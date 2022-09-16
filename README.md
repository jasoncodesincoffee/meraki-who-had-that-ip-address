# Instructions
This script solves the problem of finding a device given an IP address that it had at a certain moment in time.

## Use Case
Let's say that you use Umbrella for DNS-layer security and you integrate that into your Meraki Dashboard. If you receive a security event in Umbrella for a device in a Meraki Dashboard the log will provide you the identity (which will include the Meraki network name), timestamp of the event, and the IP address the device had at the time of the event.

Because of DHCP lease times, the IP address of the device may have changed by the time you investigate. The script allows you to use the information in the Umbrella log to find the device in question and optionally allow you to apply a block policy to it, if need be.

##How It Works
The script needs a network ID, timestamp, and IP address. Once supplied with this information the script will search the event log for DHCP leases provided for that IP at the closest instance prior to the timestamp provided.
 
 Search for network can return best match or list of best matches.
 
 Once the result is given there will be an option to apply a block policy to this client, if desired.
 
 API key can be passed as an argument or absent there it will use the env var of <<MERAKI_DASHBOARD_API_KEY>>
 
 usage: 
 ```
        python3 find_device.py [-o] orgId
 
        python3 find_device.py [-o] orgId [-k, --api_key] apiKey
```
