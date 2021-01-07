from __future__ import annotations
"""Support for animated stickers
"""
from typing import Tuple, List
import gzip
import json
import asyncio
from pyppeteer import launch
from PIL import Image
from pathlib import Path
THISDIR = str(Path(__file__).resolve().parent)


def convertTGS2PIL(fileName: str) -> Tuple[List[Image.Image], float]:
	"""Convert a tgs to gif

	Args:
		fileName (str): file path of the tgs

	Returns:
		Tuple[List[Image.Image], float]: pil images to write to gif/ webp and duration
	"""
	archive = gzip.open(fileName, "rb")
	lottie = json.load(archive)
	duration, numFrames = asyncio.get_event_loop(
	).run_until_complete(recordLottie(json.dumps(lottie)))
	images = []
	for frame in range(0, numFrames, 2):
		images.append(Image.open("temp/temp{}.png".format(frame)))
	return images, duration

def convertTGS2GIF(images: List[Image.Image], duration:float, newFileName: str):
	"""Convert to gif

	Args:
		images (List[Image.Image]): list of pil images to write
		duration (float): duration of the gif
		newFileName (str): name of the file to write
	"""
	images[0].save(newFileName, save_all=True, append_images=images[1:],
	duration=duration*1000/len(images), loop=0, transparency=0, disposal=2)

def convertTGS2Webp(images: Image.Image, duration:float, newFileName: str):
	"""Convert to webp

	Args:
		images (List[Image.Image]): list of pil images to write
		duration (float): duration of the gif
		newFileName (str): name of the file to write
	"""
	images[0].save(newFileName, save_all=True, append_images=images[1:],
	duration=int(duration*1000/len(images)), loop=0)


async def recordLottie(lottieData: str) -> Tuple[int, int]:
	"""Record the lottie data to a set of images

	Args:
		lottieData (str): lottie data as string

	Returns:
		Tuple[int, int]: duration and number of frames
	"""
	lottie = json.loads(lottieData)
	html = open(THISDIR + "/animate.html").read().replace("lottieData",
	lottieData).replace("WIDTH", str(lottie["w"])).replace("HEIGHT", str(lottie["h"]))
	browser = await launch(headless=True,
	options={'args': ['--no-sandbox', "--disable-web-security",
	"--allow-file-access-from-files"]}) # yapf: disable
	page = await browser.newPage()
	await page.setContent(html)
	await page.waitForSelector('.ready')
	duration = await page.evaluate("() => duration")
	numFrames = await page.evaluate("() => numFrames")
	pageFrame = page.mainFrame
	rootHandle = await pageFrame.querySelector('#root')
	# Take a screenshot of each frame
	for count in range(0, numFrames, 2):
		await rootHandle.screenshot({
		'path': 'temp/temp{}.png'.format(count), "omitBackground": True, })
		await page.evaluate("animation.goToAndStop({}, true)".format(count + 1))
	return duration, numFrames
