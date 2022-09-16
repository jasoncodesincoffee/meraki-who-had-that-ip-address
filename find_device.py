import asyncio
import sys
import getopt
import os
import meraki.aio
import dateutil.parser as parser
from datetime import datetime, timezone
import pandas as pd
from fuzzywuzzy import process
import re

READ_ME = '''
The script needs a network ID, timestamp, and IP address. Once supplied with this information the script
 will search the event log for DHCP leases provided for that IP at the closest instance prior to the timestamp
 provided.
 
 Search for network can return best match or list of best matches.
 
 Once the result is given there will be an option to apply a block policy to this client, if desired.
 
 API key can be passed as an argument or absent there it will use the env var of <<MERAKI_DASHBOARD_API_KEY>>
 
 usage: python3 find_device.py [-o] orgId
        python3 find_device.py [-o] orgId [-k, --api_key] apiKey
'''
#####################################################
#
# Global variables
#
#####################################################
RETRIES = 5 # number of retries when rate limits apply
TOTAL_PAGES = -1 # number of pages from network event log (-1 for all pages)
PER_PAGE_RESULTS = 1000 # number of results per page from network event log


def print_help():
    lines = READ_ME.split('\n')
    for line in lines:
        print(f'# {line}')

     
#####################################################
#
# Prompts inputs for date/time and validates
#
#####################################################
def get_event_time():
    while True:
        print("Remember, times for events will be in UTC")
        month = input("Enter the month ('mm') which the event occurred.\n")
        if (int(month) > 0 and int(month) < 13) and len(month) == 2:
            break
        else:
            print("Invalid month entered. Please enter it again.")

    while True:
        print("Remember, times for events will be in UTC")
        day = input("Enter the day ('dd') of the month which the event occurred.\n")
        if (int(day) > 0 and int(day) < 32) and len(day) == 2:
            break
        else:
            print("Invalid day entered. Please enter it again.")

    current_year = datetime.now().year
    while True:
        year_input = input("Enter the year ('yyyy') which the event occurred.\n")
        if year_input.isdigit():
            match = re.match(r'.*([1-2][0-9]{3})', year_input)
            year = int(match.group(0))
            if 1000 <= year <= current_year:
                break
            else:
                print("Invalid year entered. Please try again.")
        else:
            print("Not a valid year entered. Please try again.")

    while True:
        print("Remember, times for events will be in UTC")
        time_format = "%H:%M"
        event_time = input("Enter the time ('hh:mm' with hour 0-24) of the event. (Ex. 1:45pm will be '13:45')\n")
        try:
            datetime.strptime(event_time, time_format)
            break
        except ValueError:
            print("The time entered is not in the correct format. Please try again.")
            continue

    date_text = month+"-"+day+"-"+year_input+" "+event_time+" +0000"
    event_date = parser.parse(date_text)

    if event_date.timestamp() > datetime.now(timezone.utc).timestamp():
        print("Time/date entered is in the future. Please try again.")
        get_event_time()

    return event_date


def prompts():
    event_date = get_event_time()

    # validates IP address pattern
    pattern = "^((25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])\.){3}(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])$"

    while True:
        ip_addr = input("What is the IP address to search for?\n")
        print("checking IP for valid format....")
        validate = re.search(pattern, ip_addr)
        if validate:
            print("IP is in a valid format.")
            break
        else:
            print("That is an invalid IP address. Please enter it again.")

    return ip_addr, event_date

   
#####################################################
#
# Search function. Uses fuzzy matching to find result(s)
# to search pattern input from user.
#
#####################################################
def search_func(networks):
    net_list = []
    for network in networks:
        name = network["name"]
        net_list.append(name)

    while True:
        search_text = input("Please enter the network name to search for: ")
        print("Do you want to return the best match or list of best matches:"
              "\n\nNUMBER\tOPERATION"
              "\n1\tReturn best search result"
              "\n2\tReturn list of 10 best results")
        search_selection = input("Selection: ")
        if int(search_selection) == 1:
            highest = process.extractOne(search_text, net_list)
            print("NETWORK NAME, MATCH CONFIDENCE")
            print(highest)
            correct = input("Is the match above the correct network? (y/n): ")
            if str.lower(correct) == "y":
                selected_network_name = highest[0]
                break
            elif str.lower(correct) == "n":
                print("Starting search again...")
                continue
            else:
                print("Invalid selection. Starting search again.")
        elif int(search_selection) == 2:
            best = process.extractBests(search_text, net_list)
            best = pd.DataFrame(best, columns=["NETWORK NAME", "MATCH CONFIDENCE"])
            best10 = best.head(10)
            best10.index.name = "ROW #"
            print(best10)
            while True:
                row_selection = input("If the network needed is in the results then enter the row "
                                      "number of the result. Otherwise enter 'n' to search again: ")
                if str.lower(row_selection) == "n":
                    search_func(networks)
                elif row_selection.isdigit():
                    if 0 <= int(row_selection) < len(best10.index)-1:
                        selected_network_name = best10.loc[int(row_selection), "NETWORK NAME"]
                        print(f'The selected network is {selected_network_name}.')
                        break
                else:
                    print("The selection is invalid. Please try again.")
                    continue
            break
        else:
            print("Invalid selection. Please try again.")

    return selected_network_name


def search_networks(networks):
    ip_addr, event_date = prompts()

    while True:
        print("Enter a selection below if you want to search for a network or enter the network ID, if known:"
              "\n\nNUMBER\tOPERATION"
              "\n1\tEnter network ID"
              "\n2\tSearch for network\n")
        net_selection = input("Selection: ")

        if int(net_selection) == 1:
            net_id = input("Enter network ID (must begin with 'L_' or 'N_' and is case sensitive): ")
            break
        elif int(net_selection) == 2:
            net_name = search_func(networks)
            net_id = [network['id'] for network in networks if network['name'] == net_name]
            net_id = net_id[0]
            break
        else:
            print("That is an invalid selection. Please enter the selection again.")

    return ip_addr, event_date, net_id


async def main(argv):
    try:
        opts, args = getopt.getopt(argv, "hok:", ["help", "api_key="])
        if not (len(sys.argv[1:]) >= 1):
            print('****** # ERROR: Incorrect number of parameters given ******')
            print_help()
            sys.exit()
    except getopt.GetoptError:
        print_help()
        sys.exit(2)
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            print_help()
            sys.exit()
        elif opt == "-o":
            org_id = args[0]
        elif opt in ("-k", "--api_key"):
            apikey = arg
        else:
            print_help()
            sys.exit(2)

    if 'apikey' in locals():
        api_key = apikey
    else:
        api_key = os.environ.get("MERAKI_DASHBOARD_API_KEY")

    async with meraki.aio.AsyncDashboardAPI(
        log_file_prefix=__file__[:-3],
        output_log=False,
        print_console=False,
        maximum_retries=RETRIES,
        api_key=api_key
    ) as aiomeraki:

        networks = await aiomeraki.organizations.getOrganizationNetworks(org_id)
        search_param = {}
        search_param['ip_addr'], search_param['event_date'], search_param['netId'] = search_networks(networks)

        end_event_string = search_param['event_date'].strftime("%Y-%m-%dT%H:%M:%S.%fZ")

        print("\nRetrieving DHCP lease events for selected network....\n"
              "This may take some time depending on the number of events and \n"
              "the global variables set...")

        try:
            events = await aiomeraki.networks.getNetworkEvents(search_param['netId'],
                                                               productType="appliance",
                                                               includedEventTypes=['dhcp_lease'],
                                                               total_pages=TOTAL_PAGES,
                                                               perPage=PER_PAGE_RESULTS,
                                                               endingBefore=end_event_string)
        except meraki.AsyncAPIError as e:
            print(f'Meraki API error: {e}')
        except Exception as e:
            print(f'The following error has occurred: {e}')

        for event in events['events']:
            if event['eventData']['ip'] == search_param['ip_addr']:
                found_device_details = {
                    'ts': event['occurredAt'],
                    'clientId': event['clientId'],
                    'clientDescription': event['clientDescription'],
                    'clientIp': event['eventData']['ip'],
                    'vlan': event['eventData']['vlan']
                }
                break

        if 'found_device_details' in locals():
            try:
                device_info = await aiomeraki.networks.getNetworkClient(search_param['netId'], found_device_details['clientId'])
            except meraki.AsyncAPIError as e:
                print(f'Meraki API error: {e}')
            except Exception as e:
                print(f'The following error has occurred: {e}')

            print("\n---- DEVICE FOUND ----\n"
                  "DEVICE DETAILS\n"
                  f"Device DHCP lease found at {found_device_details['ts']}\n"
                  f"The client description is {found_device_details['clientDescription']}\n"
                  f"Client ID is {found_device_details['clientId']} with a MAC address of {device_info['mac']}\n"
                  f"It had an IP of {found_device_details['clientIp']} and was on VLAN {found_device_details['vlan']}\n\n"
                  )
            while True:
                block = input("Would you like to apply a block policy to this client? y/n: ")
                if block.lower() == 'y':
                    try:
                        await aiomeraki.networks.updateNetworkClientPolicy(search_param['netId'], found_device_details['clientId'], devicePolicy='Blocked')
                        print(f"\nA block policy has been successfully applied to {found_device_details['clientDescription']}.")
                    except Exception as e:
                        print(f'The following error has occurred: {e}')
                        sys.exit(0)
                    break
                elif block.lower() == 'n':
                    print("\nThe identified client WILL NOT be blocked.")
                    break
                else:
                    print("\nThat is not a valid option. Please try again.")
        else:
            print("\nNo logs matching the timestamp, network, and IP address were found\n"
                  "Please check the input data and try again. \n"
                  "Additionally, the event may be too far in the past or the global variables may need to be adjusted")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
