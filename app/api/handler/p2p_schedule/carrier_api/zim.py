from datetime import datetime, timedelta
from typing import Iterator, Optional, Generator

from fastapi import BackgroundTasks

from app.api.schemas.schema_request import SearchRange, StartDateType
from app.api.schemas.schema_response import Cutoff, Leg, PointBase, Schedule, Service, Transportation, Voyage
from app.internal.http.http_client_manager import HTTPClientWrapper
from app.internal.setting import Settings

TRANSPORT_TYPE: dict = {'Land Trans': 'Truck', 'Feeder': 'Feeder', 'TO BE NAMED': 'Vessel', 'BAR': 'Barge'}


def map_imo(leg_imo: str | None, vessel_name: str | None, line: str | None, transport: str) -> str:
    """Map the transportation Details"""
    if leg_imo and vessel_name != 'TO BE NAMED' and transport != 'Truck':
        return leg_imo
    elif (line == 'UNK' and leg_imo is None and transport != 'Truck') or transport == 'Feeder':
        return '9'
    elif transport == 'Truck':
        return '3'
    else:
        return '1'


def process_leg_data(leg_task: list, check_nearest_pol_etd: tuple) -> list:
    leg_list: list = [Leg.model_construct(
        pointFrom=PointBase.model_construct(locationName=leg['departurePortName'], locationCode=leg['departurePort']),
        pointTo=PointBase.model_construct(locationName=leg['arrivalPortName'], locationCode=leg['arrivalPort']),
        etd=(etd := leg['departureDate']),
        eta=(eta := leg['arrivalDate']),
        transitTime=int((datetime.fromisoformat(eta) - datetime.fromisoformat(etd)).days),
        transportations=Transportation.model_construct(
            transportType=(transport := TRANSPORT_TYPE.get(leg['vesselName'], 'Vessel')),
            transportName=(vessel_name := leg['vesselName']), referenceType='IMO',
            reference=map_imo(leg_imo=leg.get('lloydsCode'), vessel_name=vessel_name, line=leg.get('line'),
                              transport=transport)),
        services=Service.model_construct(serviceCode=leg['line']) if (voyage_num := leg.get('voyage')) else None,
        cutoffs=Cutoff.model_construct(cyCutoffDate=cyoff, docCutoffDate=leg.get('docClosingDate'),
                                       vgmCutoffDate=leg.get('vgmClosingDate'))
        if (cyoff := leg.get('containerClosingDate')) or leg.get('docClosingDate') or leg.get(
            'vgmClosingDate') else None,
        voyages=Voyage.model_construct(internalVoyage=voyage_num + leg['leg'] if voyage_num else None,
                                       externalVoyage=leg.get('consortSailingNumber'))) for leg in leg_task if
        leg['legOrder'] >= check_nearest_pol_etd[0]]
    return leg_list


def process_schedule_data(task: dict, direct_only: bool | None, vessel_imo: str, service: str, tsp: str) -> Iterator:
    """Map the schedule and leg body"""
    check_service_code: bool = any(
        service == services['line'] for services in task['routeLegs'] if services.get('voyage')) if service else True
    check_transshipment: bool = task['routeLegCount'] > 1
    check_vessel_imo: bool = any(
        imo for imo in task['routeLegs'] if imo.get('lloydsCode') == vessel_imo) if vessel_imo else True
    transshipment_port: bool = any(
        tsport['departurePort'] == tsp for tsport in task['routeLegs'][1:]) if check_transshipment and tsp else False
    if (transshipment_port or not tsp) and (direct_only is None or direct_only != check_transshipment) and (
            check_service_code or not service) and check_vessel_imo:
        transit_time: int = task['transitTime']
        first_point_from: str = task['departurePort']
        check_nearest_pol_etd: tuple = next(
            (leg['legOrder'], leg['departureDate']) for leg in task['routeLegs'][::-1] if
            leg['departurePort'] == first_point_from)
        last_point_to: str = task['arrivalPort']
        last_eta: str = task['arrivalDate']
        schedule_body = Schedule.model_construct(scac='ZIMU', pointFrom=first_point_from, pointTo=last_point_to,
                                                 etd=check_nearest_pol_etd[1], eta=last_eta,
                                                 transitTime=transit_time, transshipment=check_transshipment,
                                                 legs=process_leg_data(leg_task=task['routeLegs'],
                                                                       check_nearest_pol_etd=check_nearest_pol_etd))
        yield schedule_body


async def get_zim_access_token(client: HTTPClientWrapper, background_tasks: BackgroundTasks, token_url: str,
                               api_key: str, client_id: str, secret: str) -> str:
    headers: dict = {'Ocp-Apim-Subscription-Key': api_key}
    params: dict = {'grant_type': 'client_credentials', 'client_id': client_id, 'client_secret': secret,
                    'scope': 'Vessel Schedule'}
    response_token: dict = await anext(
        client.parse(background_tasks=background_tasks, method='POST', url=token_url, headers=headers, data=params,
                     expire=timedelta(minutes=55), namespace='zim token'))
    return response_token['access_token']


async def get_zim_p2p(client: HTTPClientWrapper, background_task: BackgroundTasks, api_settings: Settings,
                      pol: str,
                      pod: str,
                      search_range: SearchRange, start_date_type: StartDateType,
                      scac: Optional[str] = None,
                      direct_only: Optional[bool] = None,
                      departure_date: Optional[datetime.date] = None, arrival_date: Optional[datetime.date] = None,
                      vessel_imo: Optional[str] = None, service: Optional[str] = None,
                      tsp: Optional[str] = None) -> Generator:
    # Construct request parameters
    params: dict = {
        'originCode': pol,
        'destCode': pod,
        'fromDate': str(departure_date or arrival_date),
        'toDate': (departure_date + timedelta(days=int(search_range.duration))).strftime(
            '%Y-%m-%d') if start_date_type == StartDateType.departure else (
            arrival_date + timedelta(days=int(search_range.duration))).strftime('%Y-%m-%d'),
        'sortByDepartureOrArrival': start_date_type
    }

    # Define a function to generate schedule results
    def generate_schedule(data: dict) -> Generator:
        for task in data.get('response', {}).get('routes', []):
            for result in process_schedule_data(task=task, direct_only=direct_only, vessel_imo=vessel_imo,
                                                service=service, tsp=tsp):
                yield result

    # Fetch access token
    token: str = await get_zim_access_token(
        client=client,
        background_tasks=background_task,
        token_url=api_settings.zim_turl,
        api_key=api_settings.zim_token.get_secret_value(),
        client_id=api_settings.zim_client.get_secret_value(),
        secret=api_settings.zim_secret.get_secret_value()
    )

    headers: dict = {
        'Ocp-Apim-Subscription-Key': api_settings.zim_token.get_secret_value(),
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json'
    }

    # Fetch data from the API
    response_json: dict = await anext(
        client.parse(
            background_tasks=background_task,
            method='GET',
            url=api_settings.zim_url,
            params=params,
            headers=headers,
            namespace='zim original response'
        )
    )

    # Validate response and return the schedule generator if data is available
    if response_json:
        return generate_schedule(data=response_json)
