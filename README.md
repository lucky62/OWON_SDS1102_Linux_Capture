# OWON_SDS1102_Linux_Capture

Python program to download measured data from OWON SDS1102 oscilloscope.

It was created by some reverse engeneering and with AI support.

Tested on Linux Mint 22.3 Zena, Python 3.12.3

Scope connection via ttyUSB0 is hardcoded.


<img width="775" height="645" alt="image" src="https://github.com/user-attachments/assets/ecdaa203-41f8-41e1-8c44-ded1e888d781" />


## Features:
- One time download of measured data from scope
- Continuous download (Start, Stop)
- Save downloaded data to the files (image and JSON)
- Time Zooming and Panning

### JSON file example:
```
{
    "TIMEBASE": {
        "SCALE": "20us",
        "HOFFSET": 0
    },
    "SAMPLE": {
        "FULLSCREEN": 7600,
        "SLOWMOVE": -1,
        "DATALEN": 10000,
        "SAMPLERATE": "(25MS/s)",
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
            "OFFSET": -94,
            "FREQUENCE": 23291.92578,
            "INVERSE": "OFF"
        },
        {
            "NAME": "CH2",
            "DISPLAY": "OFF",
            "Current_Rate": 10000.0,
            "Current_Ratio": 24.414063,
            "Measure_Current_Switch": "OFF",
            "COUPLING": "DC",
            "PROBE": "1X",
            "SCALE": "1.00V",
            "OFFSET": -100,
            "FREQUENCE": 23437.50195,
            "INVERSE": "OFF"
        }
    ],
    "DATATYPE": "WAVEDEPMEM",
    "RUNSTATUS": "STOP",
    "IDN": "OWON,SDS1102,2022455,V4.0.1",
    "MODEL": "110200101"
}
```

## License:
- totally free for any use.
