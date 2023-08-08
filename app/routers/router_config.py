from functools import cache
from app import config
from fastapi import HTTPException
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse
from typing import Literal
import httpx
import logging
import orjson


@cache
def get_settings():
    """
    Reading a file from disk is normally a costly (slow) operation
    so we  want to do it only once and then re-use the same settings object, instead of reading it for each request.
    And this is exactly why we need to use python in built wrapper functions - cache for caching the carrier credential
    """
    return config.Settings()

class HTTPXClientWrapper:
    ##Creating new session for each request but this would probably incur performance overhead issue.
    ##even so it also has its own advantage like fault islation, increased flexibility to each request and avoid concurrency issues.
    @staticmethod
    async def get_client():
        timeout = httpx.Timeout(50.0, read=None, connect=60.0)
        limits = httpx.Limits(max_connections=None)

        """
        the reason im doing this is make sure we can yield the client to endpoint before start and explicitly close the
        client when the request is done in order to avoid any concurency issue. When we call get_schedules, then FastAPI framworks will handle dependency injection
        and the context management for it https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/

        FastAPI dependancy injection allows us to use generator functions as dependenacy
        """
        try:
            async with httpx.AsyncClient(verify=False, timeout=timeout, limits=limits) as client:
                # yield the client to the endpoint function
                logging.info(f'Client Session Started')
                yield client
                logging.info(f'Client Session Closed')
                # close the client when the request is done
        except Exception as e:
            logging.error(f'An error occured while making the request {e}')
            raise HTTPException(status_code=500, detail='An error occured while creating the client')

    @staticmethod
    async def call_client(client:httpx.AsyncClient, url: str,method: str = Literal['GET','POST'], params: dict = None, headers: dict = None, json: dict = None,
                          data: dict = None, stream: bool = False):
        if not stream:
            response = await client.request(method=method, url=url, params=params, headers=headers, json=json,data=data)
            yield response
        else:
            """
            At the moment Only Maersk('MAEU', 'SEAU', 'SEJJ', 'MCPU', 'MAEI') need consumer to stream the response
            """
            client_request = client.build_request(method=method, url=url, params=params, headers=headers, data=data)
            stream_request = await client.send(client_request, stream=True)
            result = StreamingResponse(stream_request.aiter_lines(), background=BackgroundTask(stream_request.aclose))
            if result.status_code == 200:
                async for data in result.body_iterator:
                    response = orjson.loads(data)
                    yield response
            else:
                yield None
