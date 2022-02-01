"""Sticker download functions used by the module entry point."""

from __future__ import annotations

import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from json.decoder import JSONDecodeError
from pathlib import Path
from sys import exit as sysexit
from typing import Any

from emoji import demojize

from . import caching
from .convert import assureDirExists, convertTgs, convertWebp


class Sticker:
	"""Sticker instance attributes"""

	def __init__(
		self,
		name: str = "None",
		link: str = "None",
		emoji: str = "😀",
		fileType="webp",
	):
		self.name = name
		self.link = link
		self.emoji = emoji
		self.fileType = fileType

	def __repr__(self):
		return f"<Sticker:{self.name}>"

	def emojiName(self) -> str:
		"""get the emoji as a string"""
		return demojize(self.emoji)[1:-1]


class StickerDownloader:
	"""The StickerDownloader sets up the api and makes requests"""

	def __init__(self, token, session=None, multithreading=4):
		self.threads = multithreading
		self.token = token
		self.cwd = assureDirExists(Path(), "downloads")
		if session is None:
			self.session = caching.cachedSession
		else:
			self.session = session
		self.api = f"https://api.telegram.org/bot{self.token}/"
		verify = self.doAPIReq("getMe", {})
		if verify is not None and verify["ok"]:
			pass
		else:
			print("Invalid token.")
			sysexit(1)

	def doAPIReq(self, function: str, params: dict[Any, Any]) -> dict[Any, Any] | None:
		"""Use the telegram api

		Args:
			function (str): function to execute
			params (dict[Any, Any]): function parameters

		Raises:
			RuntimeError: In the event of a failure

		Returns:
			Optional[dict[Any, Any]]: api response
		"""
		urlParams = "?" + urllib.parse.urlencode(params)
		res = self.session.get(f"{self.api}{function}{urlParams}")
		try:
			res = res.json()
		except JSONDecodeError:
			res = {"ok": False, "raw": res}
		if res["ok"]:
			return res

		print(f'API method {function} with params {params} failed. Error: "{res["description"]}"')
		return None

	def getSticker(self, fileData: dict[Any, Any]) -> Sticker:
		"""Get sticker info from the server

		Args:
			fileData (dict[Any, Any]): sticker id

		Returns:
			Sticker: Sticker instance
		"""
		info = self.doAPIReq("getFile", {"file_id": fileData["file_id"]})
		if info is not None:
			filePath = info["result"]["file_path"]
			file = Sticker(
				name=filePath.split("/")[-1],
				link=f"https://api.telegram.org/file/bot{self.token}/{filePath}",
				emoji=fileData["emoji"],
				fileType=filePath.split(".")[-1],
			)
			return file
		return Sticker()

	def getPack(self, packName: str) -> dict[str, Any] | None:
		"""Get a list of File objects.

		Args:
			packName (str): name of the pack

		Returns:
			dict[str, Any]: dictionary containing sticker data
		"""
		params = {"name": packName}
		res = self.doAPIReq("getStickerSet", params)
		if res is None:
			return None
		stickers = res["result"]["stickers"]
		files = []

		print(f'Starting to scrape "{packName}" ..')
		start = time.time()
		with ThreadPoolExecutor(max_workers=self.threads) as executor:
			futures = [executor.submit(self.getSticker, i) for i in stickers]
			for i in as_completed(futures):
				files.append(i.result())
		end = time.time()
		print(f"Time taken to scrape {len(files)} stickers - {end - start:.3f}s")
		print()

		pack = {
			"name": res["result"]["name"].lower(),
			"title": res["result"]["title"],
			"files": files,
		}
		return pack

	def downloadSticker(self, path: Path, link: str) -> int:
		"""Download a sticker from the server.

		Args:
			path (Path): the path to write to
			link (str): the url to the file on the server

		Returns:
			int: path.write_bytes(res.content)
		"""
		return path.write_bytes(self.session.get(link).content)

	def downloadPack(self, pack: dict[str, Any]) -> list[str]:
		"""Download a sticker pack.

		Args:
			pack (dict[str, Any]): dictionary representing a sticker pack

		Returns:
			list[str]: list of file paths each sticker is written to
		"""
		swd = assureDirExists(self.cwd, pack["name"])
		downloads = []
		print(f'Starting download of "{pack["name"]}" into {swd}')
		start = time.time()
		with ThreadPoolExecutor(max_workers=self.threads) as executor:
			futures = [
				executor.submit(
					self.downloadSticker,
					assureDirExists(swd, sticker.fileType)
					/ (
						f'{sticker.name.split("_")[-1].split(".")[0]}+{sticker.emojiName()}'
						f".{sticker.fileType}"
					),
					link=sticker.link,
				)
				for sticker in pack["files"]
			]
			for i in as_completed(futures):
				downloads.append(i.result())
		self.session.close()

		end = time.time()
		print(f"Time taken to download {len(downloads)} stickers - {end - start:.3f}s")
		print()
		return downloads

	def convertPack(self, packName: str, frameSkip: int = 1, scale: float = 1, noCache=False):
		"""Convert the webp to gif and png; tgs to gif, webp (webp_animated) and png.

		Args:
			packName (str): name of the directory to convert
			frameSkip (int, optional): skip n number of frames in the interest of
			optimisation with a quality trade-off. Defaults to 1.
			scale (float, optional): upscale/ downscale the images produced. Intended
			for optimisation with a quality trade-off. Defaults to 1.
			noCache (bool, optional): set to true to disable cache. Defaults to False.
		"""
		if not noCache and caching.verifyConverted(packName):
			return
		# Make directories
		swd = assureDirExists(self.cwd, packName)

		# Convert Stickers
		start = time.time()
		total = len([x for x in Path(swd).glob("**/*") if x.is_file()])

		print(f'Converting stickers "{packName}"...')

		# tgs
		converted = convertedTgs = convertTgs(swd, self.threads, frameSkip=frameSkip, scale=scale)

		# webp
		convertedWebp = convertWebp(swd, self.threads)
		converted += convertedWebp

		end = time.time()
		print(f"Time taken to convert {converted}/{total} stickers (total) - {end - start:.3f}s")
		print()

		caching.createConverted(
			packName,
			data={
				"version": 1,
				"info": {
					"packName": packName,
					"frameSkip": frameSkip,
					"scale": scale,
					"swd": swd.as_posix(),
				},
				"converted": {
					"static": convertedWebp,
					"animated": convertedTgs,
					"total": total,
				},
			},
		)
