from app.background_tasks import db
from app.schemas import schema_response
from app.config import load_yaml,log_queue_listener
from fastapi import status,HTTPException,BackgroundTasks,Response
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError,ResponseValidationError
from uuid import UUID,uuid4
from typing import Literal,Generator,Callable,AsyncGenerator,Dict,Any
from datetime import timedelta
import httpx
import logging
import orjson
import asyncio
import time



QUEUE_LISTENER = log_queue_listener()
async def startup_event():
    # Global Client Setup
    global httpx_client
    QUEUE_LISTENER.start()
    await db.initialize_database()
    httpx_client = HTTPXClientWrapper()
    logging.info("HTTPX Client initialized",extra={'custom_attribute':None})

async def shutdown_event():
    global httpx_client
    if httpx_client:
        await httpx_client.aclose()
        logging.info("HTTPX Client closed", extra={'custom_attribute': None})
    QUEUE_LISTENER.stop()



"""Given that each of the 7000 employees performs 7000 searches per hour, this amounts to 7000×7000=49,000,000
7000×7000=49,000,000 searches per hour. To break it down per second:49,000,000searches / 3600 seconds ≈ 13,611 searches per second

However, this doesn't mean we need 13,611 connections simultaneously because these searches will be distributed over time and can reuse TCP connections and keep-alive.

If we estimate that each search takes around 1 second, and considering we need to handle 13,611 searches per second, you'd start with a similar number for max connections. 
However, given that not all searches will happen exactly at the same time and some connections can be reused, we can reduce this number.

A good starting point is to use around 10-20% of the peak searches per second as concurrent connections.
Therefor,  10% of 13,611 is approximately 1361 connections.
We can adjust this number based on the actual performance and server capacity.
Since KN employees are performing searches frequently (every hour), setting a higher keep-alive expiry can help reuse connections effectively."""

logging.getLogger("httpx").setLevel(logging.WARNING)
KN_PROXY:httpx.Proxy = httpx.Proxy("http://proxy.eu-central-1.aws.int.kn:80")
HTTPX_TIMEOUT = httpx.Timeout(load_yaml()['data']['connectionPoolSetting']['elswhereTimeOut'],pool=load_yaml()['data']['connectionPoolSetting']['connectTimeOut'], connect=load_yaml()['data']['connectionPoolSetting']['connectTimeOut'])
HTTPX_LIMITS = httpx.Limits(max_connections=load_yaml()['data']['connectionPoolSetting']['maxClientConnection'],
                            max_keepalive_connections=load_yaml()['data']['connectionPoolSetting']['maxKeepAliveConnection'],keepalive_expiry=load_yaml()['data']['connectionPoolSetting']['keepAliveExpiry'])
# HTTPX_ASYNC_HTTP = httpx.AsyncHTTPTransport(retries=3,verify=False,limits=HTTPX_LIMITS)
HTTPX_ASYNC_HTTP = httpx.AsyncHTTPTransport(retries=3,proxy = KN_PROXY,verify=False,limits=HTTPX_LIMITS)


class HTTPXClientWrapper(httpx.AsyncClient):
    __slots__ = ('session_id')
    def __init__(self):
        super().__init__(timeout=HTTPX_TIMEOUT, transport=HTTPX_ASYNC_HTTP)
        self.session_id: str = str(uuid4())

#Individual Client Session Setup
    @classmethod
    async def get_individual_httpx_client_wrapper(cls) -> Generator:
        async with cls() as standalone_client:
            logging.info(f'Client Session Started - {standalone_client.session_id}')
            try:
                yield standalone_client
            except (ConnectionError,httpx.ConnectTimeout,httpx.ConnectError) as connect_error:
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,detail=f'{connect_error.__class__.__name__}:{connect_error}')
            except ValueError as value_error:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,detail=f'{value_error.__class__.__name__}:{value_error}')
            except RequestValidationError as request_error:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail=f'{request_error.__class__.__name__}:{request_error}')
            except ResponseValidationError as response_error:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,detail=f'{response_error.__class__.__name__}:{response_error}')
            except Exception as eg:
                logging.error(f'{eg.__class__.__name__}:{eg.args}')
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,detail=f'An error occurred while creating the client - {eg.args}')
            logging.info(f'Client Session Closed - {standalone_client.session_id}')

    async def parse(self, url: str, method: Literal['GET', 'POST'] = 'GET', params: dict = None, headers: dict = None,json: dict = None, token_key: str|UUID = None, data: dict = None,
                    background_tasks: BackgroundTasks = None,expire: timedelta = timedelta(hours=load_yaml()['data']['backgroundTasks']['scheduleExpiry']),stream: bool = False) -> AsyncGenerator[Dict[str, Any], None]:
        """Fetch the file from carrier API and deserialize the json file """
        if not stream:
            async for response in self.handle_standard_response(url, method, params, headers, json, data, token_key,background_tasks, expire):
                yield response
        else:
            async for response in self.handle_streaming_response(url, method, params, headers, data, token_key,background_tasks, expire):
                yield response

    async def handle_standard_response(self, url: str, method: str, params: dict, headers: dict, json: dict, data: dict, token_key: str, background_tasks: BackgroundTasks, expire: timedelta) -> AsyncGenerator[Dict[str,Any],None]:
        response = await self.request(method=method, url=url, params=params, headers=headers, json=json, data=data)
        logging.info(f'{method} {response.url} {response.http_version} {response.status_code} {response.reason_phrase} elapsed_time={response.elapsed.total_seconds()}s')
        if response.status_code == status.HTTP_206_PARTIAL_CONTENT:
            yield response
        elif response.status_code == status.HTTP_200_OK:
            response_json = response.json()
            if background_tasks:
                background_tasks.add_task(db.set, key=token_key, value=response_json, expire=expire)
            yield response_json
        elif response.status_code in (status.HTTP_500_INTERNAL_SERVER_ERROR, status.HTTP_502_BAD_GATEWAY):
            logging.critical(f'Unable to connect to {response.url}')
            yield None
        else:
            yield None


    async def handle_streaming_response(self, url: str, method: str, params: dict, headers: dict, data: dict,token_key: str, background_tasks: BackgroundTasks, expire: timedelta) -> AsyncGenerator[Dict[str, Any],None]:
        client_request = self.build_request(method=method, url=url, params=params, headers=headers, data=data)
        stream_request = await self.send(client_request, stream=True)
        if stream_request.status_code == status.HTTP_200_OK:
            try:
                async for data in stream_request.aiter_lines():
                    response = orjson.loads(data)
                    logging.info(f'{method} {stream_request.url} {stream_request.http_version} {stream_request.status_code} {stream_request.reason_phrase} elapsed_time={stream_request.elapsed.total_seconds()}s')
                    if background_tasks:
                        background_tasks.add_task(db.set, key=token_key, value=response, expire=expire)
                    yield response

            finally:
                await stream_request.aclose()
        else:
            yield None


    def gen_all_valid_schedules(self,correlation:str|None,response:Response,product_id:UUID,matrix:Generator,point_from:str,point_to:str,background_tasks:BackgroundTasks,task_exception:bool):
        """Validate the schedule and serialize hte json file excluding the field without any value """
        flat_list:list = [item for row in matrix if not isinstance(row, Exception) and row is not None for item in row]
        count_schedules:int = len(flat_list)
        response.headers.update({"X-Correlation-ID": str(correlation), "Cache-Control": "public, max-age=7200" if count_schedules >0 else "no-cache, no-store, max-age=0, must-revalidate",
                                 "KN-Count-Schedules": str(count_schedules)})
        if count_schedules == 0:
            final_result = JSONResponse(status_code=status.HTTP_200_OK,content=jsonable_encoder(schema_response.Error(productid=product_id,details=f"{point_from}-{point_to} schedule not found")))
        else:
            validation_start_time = time.time()
            sorted_schedules: list = sorted(flat_list, key=lambda tt: (tt['etd'], tt['transitTime']))
            final_set:dict = {'productid':product_id,'origin':point_from,'destination':point_to, 'noofSchedule':count_schedules,'schedules':sorted_schedules}
            final_validation = schema_response.PRODUCT_ADAPTER.validate_python(final_set)
            logging.info(f'total_validation_time={time.time() - validation_start_time:.2f}s Validated the schedule ')

            dump_start_time = time.time()
            final_result = schema_response.PRODUCT_ADAPTER.dump_python(final_validation,mode='json',exclude_none=True)
            logging.info(f'serialization_time={time.time() - dump_start_time:.2f}s Dump json file excluding all the fields without value ')
            if not task_exception:
                background_tasks.add_task(db.set,key=product_id,value=final_result)
        return final_result


#Global Client Setup
async def get_global_httpx_client_wrapper() -> Generator[HTTPXClientWrapper, None, None]:
    """Global ClientConnection Pool  Setup"""
    try:
        yield httpx_client
    except (ConnectionError, httpx.ConnectTimeout, httpx.ConnectError) as connect_error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=f'{connect_error.__class__.__name__}:{connect_error}')
    except ValueError as value_error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f'{value_error.__class__.__name__}:{value_error}')
    except RequestValidationError as request_error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f'{request_error.__class__.__name__}:{request_error}')
    except ResponseValidationError as response_error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f'{response_error.__class__.__name__}:{response_error}')
    except Exception as eg:
        logging.error(f'{eg.__class__.__name__}:{eg.args}')
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,detail=f'An error occurred while creating the client - {eg.args}')

class AsyncTaskManager():
    """Currently there is no built in  python class and method that we can prevent it from cancelling all conroutine tasks if one of the tasks is cancelled
    From BU perspective, all those carrier schedules are independent from one antoher so we shouldnt let a failed task to cancel all other successful tasks"""
    def __init__(self,default_timeout=load_yaml()['data']['connectionPoolSetting']['asyncDefaultTimeOut'],max_retries=load_yaml()['data']['connectionPoolSetting']['retryNumber']):
        self.__tasks:dict = dict()
        self.error:bool = False
        self.default_timeout:int = default_timeout
        self.max_retries:int = max_retries
    async def __aenter__(self):

        logging.info('AsyncContextManger Started - Creating conroutine tasks for requested carriers')
        return self
    async def __aexit__(self, exc_type = None, exc = None, tb= None):
        self.results = await asyncio.gather(*self.__tasks.values(), return_exceptions=True)
        logging.info('AsyncContextManger Closed - Gathering And Standardizing all the schedule files obtained from carriers')
    async def _timeout_wrapper(self, coro:Callable, task_name:str):
        """Wrap a coroutine with a timeout and retry logic."""
        retries:int = 0
        adjusted_timeout = self.default_timeout
        while retries < self.max_retries:
            try:
                return await asyncio.wait_for(coro(), timeout=self.default_timeout)
            except (asyncio.TimeoutError,asyncio.CancelledError,httpx.ReadTimeout,httpx.ReadError,httpx.ConnectTimeout,):
                """Due to timeout, the coroutine task is cancelled. Once its cancelled, we retry it 3 times"""
                logging.error(f"{task_name} timed out after {self.default_timeout} seconds. Retrying {retries + 1}/{self.max_retries}...")
                retries += 1
                adjusted_timeout += 3
                await asyncio.sleep(1)  # Wait for 1 sec before the next retry
        logging.error(f"{task_name} reached maximum retries. the schedule  wont be cached anything")
        self.error = True
        # return coro()
        return None

    def create_task(self, name:str,coro:Callable):
        self.__tasks[name] = asyncio.create_task(self._timeout_wrapper(coro=coro,task_name=name))

    def results(self) -> Generator:
        logging.info('Gathering and standarding the schedule format')
        return (result for result in self.results if not isinstance(result, Exception)) if self.error else self.results