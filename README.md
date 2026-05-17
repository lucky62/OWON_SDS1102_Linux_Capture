# OWON_SDS1102_Linux_Capture

Python program to download measured data from OWON SDS1102 oscilloscope.

It was created by some reverse engeneering and with AI support.

Tested on Linux Mint 22.3 Zena, Python 3.12.3

Scope connection via ttyUSB0 is hardcoded.

<img width="1503" height="937" alt="image" src="https://github.com/user-attachments/assets/91eb66c4-cb31-4232-a195-00c709541e87" />

## Features:
- One time download of measured data from scope
- Time Zooming and Panning
- Continuous download (Start, Stop)
- Save downloaded data to the files (image and JSON)
- Download and Save data in a batch with some statistics
- Settings saved to user folder, loaded at next start

### JSON file example:
```
{
    "TIMEBASE": {
        "SCALE": "200us",
        "HOFFSET": 0
    },
    "SAMPLE": {
        "FULLSCREEN": 7600,
        "SLOWMOVE": -1,
        "DATALEN": 10000,
        "SAMPLERATE": "(2.5MS/s)",
        "TYPE": "SAMPle",
        "DEPMEM": "10K",
        "SCREENOFFSET": 1200
    },
    "CHANNEL": [
        {
            "NAME": "CH1",
            "DISPLAY": "ON",
            "Current_Rate": 10000.0,
            "Current_Ratio": 488.28125,
            "Measure_Current_Switch": "OFF",
            "COUPLING": "DC",
            "PROBE": "10X",
            "SCALE": "2.00V",
            "OFFSET": -100,
            "FREQUENCE": 14608.23438,
            "INVERSE": "OFF",
            "RAW_MIN": -1120,
            "RAW_MAX": 656
        },
        {
            "NAME": "CH2",
            "DISPLAY": "ON",
            "Current_Rate": 10000.0,
            "Current_Ratio": 48.828125,
            "Measure_Current_Switch": "OFF",
            "COUPLING": "DC",
            "PROBE": "10X",
            "SCALE": "200mV",
            "OFFSET": 0,
            "FREQUENCE": 1000.0,
            "INVERSE": "OFF",
            "RAW_MIN": -80,
            "RAW_MAX": 1104
        }
    ],
    "DATATYPE": "WAVEDEPMEM",
    "RUNSTATUS": "STOP",
    "IDN": "OWON,SDS1102,2022455,V4.0.1",
    "MODEL": "110200101"
}
```

## License:
- totally free for any use
- no guarantees
