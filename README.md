# IDD_Final_Project

## Set-up 

One pi must host. The other Pis can act as instruments.

First-time set up:

```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-pi.txt
```

For the hosting Pi:
1. Set up Bluetooth speaker (can connect via VNC Viewer)
2. We use the class server. We can set up our viewer by running `python mqtt_viewer_instrument.py`

For the instrument Pis:
1. Run the corresponding publisher (`python <instrument_name>_publisher.py`)


## TO DO LIST:
- finish parsing beat/music file on the backend with generating targets for the instruments
- show beats on the frontend
- frontend: show instruments movement with real actions
- design/create physical prototypes
- create music file
