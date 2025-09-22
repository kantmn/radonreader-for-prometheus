#!/usr/bin/env python

__progname__    = "RadonEye RD200 (Bluetooth/BLE) Reader"
__version__     = "0.4.1"
__author__      = "etoten/kantmn"
__date__        = "2025-03-27"


from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from contextlib import asynccontextmanager
from datetime import datetime
import uvicorn
import time
import argparse
import logging
import sys
import asyncio
import requests
from bluepy import btle
from radon_reader_by_handle import radon_device_reader

# Logging setup
logger = logging.getLogger()
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Argparse
parser = argparse.ArgumentParser(description=__progname__)
parser.add_argument('-b','--becquerel', action='store_true', help='Display radon value in Becquerel (Bq/m^3)')
parser.add_argument('-v','--verbose', action='store_true', help='Verbose mode')
args = parser.parse_args()

# Argparse addition
parser.add_argument(
    '--radon-sensors', 
    type=str, 
    nargs='+', 
    help='List of radon sensors in the format MAC:Name'
)

args = parser.parse_args()

# Convert input list into dictionary
radonSensors = {}
if args.radon_sensors:
    for sensor in args.radon_sensors:
        if ':' in sensor:
            mac, name = sensor.split(':', 1)
            radonSensors[mac] = name
        else:
            logger.warning(f"Ignoring invalid sensor format: {sensor}")
# Sensor data
radonValue = {}

def GetRadonValue(macAdress, deviceType):
    mRadonValueBQ, mRadonValuePCi = radon_device_reader(macAdress, deviceType)

    if mRadonValueBQ > 1000 or mRadonValueBQ < 0:
        raise Exception("Very strange radon value. Debugging needed.")

    value = mRadonValueBQ if args.becquerel else mRadonValuePCi

    if len(radonValue[macAdress]) >= 10:
        radonValue[macAdress].pop(0)
    radonValue[macAdress].append(value)

def getAverageRadon(macAdress):
    readings = radonValue[macAdress]
    return round(sum(readings) / len(readings), 2) if readings else 0

def getCurrentRadon(macAdress):
    readings = radonValue[macAdress]
    return readings[-1] if readings else 0

def getLastRadon(macAdress):
    readings = radonValue[macAdress]
    return readings[-2] if len(readings) > 1 else 0

async def main():
    logger.info("Init Device Pool")
    for mac in radonSensors:
        radonValue[mac] = []

    logger.info("Starting measurement loop")
    while True:
        for t in range(9):
            for mac in radonSensors:
                for i in range(3):
                    try:
                        GetRadonValue(mac, 1)
                        logger.info(f"Round {t}: Radon of {radonSensors[mac]}({mac}) in #{i}. try is {getLastRadon(mac)}")
                        break
                    except Exception as e:
                        logger.info(f"Attempt {i+1} failed for {mac}: {e}")
            await asyncio.sleep(60)

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(main())
    yield

app = FastAPI(lifespan=lifespan)

@app.get("/metrics", response_class=PlainTextResponse)
async def get_metrics():
    timestamp = int(time.time() * 1000)
    metrics = ""
    lines = ""

    for mac in radonSensors:
        if mac in radonValue:
            name = radonSensors[mac]
            current = getCurrentRadon(mac)
            metrics += f'radon_api{{device="{name}"}} {current} {timestamp}\n'
            lines += f"{name}={current} {timestamp}\n"

    with open("radon.txt", "w") as f:
        f.write(lines)

    return metrics

if __name__ == "__main__":
    try:
        uvicorn.run(app, host="0.0.0.0", port=5000, log_level="warning")
    
    except IOError as e:
        logging.error(e)

    except KeyboardInterrupt:
        logging.info("Interrupted by user, cleaning up...")
        exit()
