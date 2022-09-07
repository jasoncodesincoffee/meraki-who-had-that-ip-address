# README
This script solves the problem of finding a device given an IP address that it had at a certain moment in time.

The script needs a network ID, timestamp, and IP address. Once supplied with this information the script
 will search the event log for DHCP leases provided for that IP at the closest instance prior to the timestamp
 provided.
 
 Search for network can return best match or list of best matches.
 
 Once the result is given there will be an option to apply a block policy to this client, if desired.
 
 API key can be passed as an argument or absent there it will use the env var of <<MERAKI_DASHBOARD_API_KEY>>
 
 usage: python3 find_device.py [-o] orgId
        python3 find_device.py [-o] orgId [-k, --api_key] apiKey
