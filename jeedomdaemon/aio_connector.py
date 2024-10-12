"""Module providing Listener & Publisher class for your daemon."""

import logging
import json
import asyncio
from typing import Callable, Awaitable
from collections.abc import Mapping
import aiohttp


class Listener():
    """
    This class allows to create an asyncio task that will open a socket server and listen to it until the task is canceled.
    `on_message` callback will be called with the message as a list as argument
    """
    def __new__(cls, *args, **kwargs):
        if not hasattr(cls, 'instance'):
            cls.instance = super().__new__(cls)
        return cls.instance

    def __init__(self, socket_host: str, socket_port: int, on_message_cb: Callable[[list], Awaitable[None]]) -> None:
        self._socket_host = socket_host
        self._socket_port = socket_port
        self._on_message_cb = on_message_cb
        self._logger = logging.getLogger(__name__)

    @staticmethod
    def create_listen_task(socket_host: str, socket_port: int, on_message_cb: Callable[[list], Awaitable[None]]):
        """ Helper function to create the listen task"""
        listener = Listener(socket_host, socket_port, on_message_cb)
        return asyncio.create_task(listener.listen())

    async def listen(self):
        """ listen function, a task should be made out of it. Don't use this function directly but use `create_listen_task()` instead"""
        try:
            server = await asyncio.start_server(self.__handle_read, self._socket_host, port=self._socket_port)

            async with server:
                self._logger.info('Listening on %s:%s', self._socket_host, self._socket_port)
                await server.serve_forever()
        except asyncio.CancelledError:
            self._logger.info("Listening cancelled")

    async def __handle_read(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self._logger.debug("Received new message on socket")
        data = await reader.read()
        message = data.decode()
        writer.close()
        self._logger.debug("Close connection")
        await writer.wait_closed()
        await self._on_message_cb(json.loads(message))

class Publisher():
    """This class allows to push information to Jeedom either immediately by calling function `send_to_jeedom` or in cycle by calling function `add_change`. For the "cycle" mode, a task must be created by calling `create_send_task` and awaited"""
    def __init__(self, callback_url: str, api_key: str, cycle: float = 0.5) -> None:
        self._jeedom_session = aiohttp.ClientSession()
        self._callback_url = callback_url
        self._api_key = api_key
        self._cycle = cycle if (cycle > 0 and cycle < 10) else 0.5
        self._logger = logging.getLogger(__name__)

        self.__changes = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self._jeedom_session.close()

    def create_send_task(self):
        """ Helper function to create the send task.

        A running loop in the current thread must exist
        """
        return asyncio.create_task(self.__send_task())

    async def test_callback(self):
        """test_callback will return true if the communication with Jeedom is successful or false otherwise"""
        try:
            async with self._jeedom_session.get(self._callback_url + '?test=1&apikey=' + self._api_key) as resp:
                if resp.status != 200:
                    self._logger.error("Please check your network configuration page: %s-%s", resp.status, resp.reason)
                    return False
        except aiohttp.ClientError as e:
            self._logger.error('Callback error: %s. Please check your network configuration page', e)
            return False
        return True

    async def __send_task(self):
        self._logger.info("Send async started with a cycle of %ss", self._cycle)
        try:
            last_send_on_error = False
            while True:
                if len(self.__changes)>0:
                    changes = self.__changes
                    self.__changes = {}

                    try:
                        if not await self.send_to_jeedom(changes):
                            await self.__merge_dict(self.__changes,changes)
                    except aiohttp.ClientError as e:
                        if last_send_on_error:
                            self._logger.error("error during send: %s", e)
                        else:
                            self._logger.debug("first time error during send: %s", e)
                            last_send_on_error = True
                        await self.__merge_dict(self.__changes,changes)
                    except TypeError as e:
                        self._logger.error("error during send: %s. No new try to send!", e)
                    else:
                        last_send_on_error = False
                await asyncio.sleep(self._cycle)
        except asyncio.CancelledError:
            self._logger.info("Send async cancelled")

    async def send_to_jeedom(self, payload):
        """
        Will send the payload provided.
        return true if successful or false otherwise
        """
        self._logger.debug('Send to jeedom: %s', payload)
        try:
            async with self._jeedom_session.post(self._callback_url + '?apikey=' + self._api_key, json=payload) as resp:
                if resp.status != 200:
                    self._logger.error('Error on send request to jeedom, return %s-%s', resp.status, resp.reason)
                    return False
            return True
        except asyncio.TimeoutError:
            self._logger.warning('Timeout on send request to jeedom')
            return False


    async def add_change(self, key: str, value):
        """
        Add a key/value pair to the payload of the next cycle, several levels can be provided at once by separating keys with `::`
        If a key already exists the value will be replaced by the newest
        """
        if key.find('::') != -1:

            changes = value
            for k in reversed(key.split('::')):
                tmp_changes = {}
                tmp_changes[k] = changes
                changes = tmp_changes
            await self.__merge_dict(self.__changes,changes)
        else:
            self.__changes[key] = value

    async def __merge_dict(self, dic1: dict, dic2: dict):
        for key,val2 in dic2.items():
            val1 = dic1.get(key) # returns None if v1 has no value for this key
            if isinstance(val1, Mapping) and isinstance(val2, Mapping):
                await self.__merge_dict(val1, val2)
            else:
                dic1[key] = val2
