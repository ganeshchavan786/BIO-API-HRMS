import frappe
import requests
# from suds.client import Client
# from zeep import Client
import json
# import xmltodict
from dateutil import parser as date_parser
from datetime import timedelta
import xml.etree.ElementTree as ET
from datetime import datetime


@frappe.whitelist(allow_guest=True)
def get_transactions_log():
	data2 = frappe.db.sql(''' SELECT name, sirial_number, user_nmae, user_password, url, sync_time, from_date FROM `tabDevice Details` WHERE active = 1 ''', as_dict=True)
	
	parsed_data = []
	for j in data2:
	# data=frappe.db.sql(''' SELECT name from `tabDevice Details` ''',as_dict=True)
	# for i in data:
		
		BioDevice = frappe.get_doc('Device Details',j.get('name'))
		serial_number = BioDevice.sirial_number
		user_name = BioDevice.user_nmae
		user_password = BioDevice.get_password('user_password')
		url = BioDevice.url
		sync_time = BioDevice.sync_time
		from_date = BioDevice.from_date
		total_min = int(sync_time) * 60

		tomorrow_date = (datetime.today() + timedelta(days=1)).strftime('%Y-%m-%d')
		
		
		if BioDevice.active:	
			webservice_url = f"{url}"	
			data =f"""
			<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:tem="http://tempuri.org/">
				<soapenv:Header/>
				<soapenv:Body>
					<tem:GetTransactionsLog>
						<tem:FromDateTime>{from_date}</tem:FromDateTime>
						<tem:ToDateTime>{tomorrow_date}</tem:ToDateTime>
						<tem:SerialNumber>{serial_number}</tem:SerialNumber>
						<tem:UserName>{user_name}</tem:UserName>
						<tem:UserPassword>{user_password}</tem:UserPassword>
						<tem:strDataList>string</tem:strDataList>
					</tem:GetTransactionsLog>
				</soapenv:Body>
			</soapenv:Envelope>
			"""
			
			headers = {
				'Content-Type': 'text/xml',
				'Accept': 'text/xml'
			}
			response = requests.post(webservice_url, headers=headers, data=data)	
				
			if response.status_code == 200:
			
				parsed_data = parse_transactions(response.text)
				create_employee_checkin_documents(parsed_data)
			# 	return {
			# 		"success": True,
			# 		"data": parsed_data
			# 		}
			# else:
			# 	return {
			# 		"success": False,
			# 		"message": f"Failed to retrieve transaction log. Status Code: {response.status_code}"
			# 		}
	if parsed_data:
		return {
			"success": True,
			"data": parsed_data
			}
	else:
		return {
			"success": False,
			"message": f"Failed to retrieve transaction log. Status Code: {response.status_code}"
			}
def parse_transactions(xml_data):
	def is_datetime(value):
		try:
			date_parser.parse(value)
			return True
		except ValueError:
			return False
	root = ET.fromstring(xml_data)
	data_dict = {}
	for elem in root.iter():
		if elem.text and elem.text.strip():
			transactions = elem.text.split('\t\r')
			for transaction in transactions:
				transaction_data = transaction.split('\t')				
				trans = [transaction_data[i:i+2] for i in range(0, len(transaction_data), 2) if transaction_data[i] != '\n']
				trans2 = [[item.strip('\n') for item in sublist] for sublist in trans]
				trans2_cleaned = [[x.replace('\n', '').replace('in', '') for x in sublist] for sublist in trans2]
				result_list = []				
				for sublist in trans2_cleaned:
					temp_dict = {}
					for item in sublist:
						if item.isdigit():
							temp_dict["device_id"] = int(item)
						
						elif not is_datetime(item):  
							temp_dict["device_id" ] = item
						else:
							temp_dict["checkin"] = item
					
						
					if "device_id" in temp_dict and "checkin" in temp_dict:  # Ensure both device_id and checkin are present before appending
						result_list.append(temp_dict)	
						# print("--------",result_list)			
				if len(result_list) >= 2:
					employee_id = check_device_id_matches_employee(result_list)					
	return employee_id

def check_device_id_matches_employee(result_list):
	employee_device_id = []
	for entry in result_list:
		device_id = entry['device_id']
		attendance_time = entry['checkin']		
		employees_with_device_id = frappe.get_all(
			"Employee",
			filters={"attendance_device_id": device_id},
			fields=["name","employee_name","default_shift"]
		)
		
		if employees_with_device_id:
			# print("-----------",employees_with_device_id)
			for employee in employees_with_device_id:
				employee_id = employee['name']
				employee_name = employee['employee_name']
				shift = employee['default_shift']
				employee_device_data = {
					"employee_id" : employee_id,
					"employee_name" : employee_name,
					"device_id" : device_id,
					"Checkin_time" : attendance_time,
					"shift" : shift
				}
				employee_device_id.append(employee_device_data)
				# print("-----------",employee_device_id)
					
		else:
			print(f"No employee found with device id")
		# print(employee_device_id,"device id....")
	return employee_device_id

def create_employee_checkin_documents(employee_device_id):
	employee_entries = {}
	for entry in employee_device_id:
		employee_id = entry['employee_id']
		checkin_date = entry['Checkin_time'].split()[0]  # Extract date only

		if employee_id not in employee_entries:
			employee_entries[employee_id] = {}

		if checkin_date not in employee_entries[employee_id]:
			employee_entries[employee_id][checkin_date] = []

		employee_entries[employee_id][checkin_date].append(entry)
		# print("------- ext",employee_entries)

	employee_checkins = []

	for employee_id, dates in employee_entries.items():
		
		for checkin_date, entries in dates.items():
			entries.sort(key=lambda x: x['Checkin_time'])  # Sort entries by time
			
			last_log_type = None  # Track last log type to determine current log type
			for i, entry in enumerate(entries):
				# print("---------------------- pp",i,entry['Checkin_time'])
				
						
				checkin_doc = frappe.new_doc("Employee Checkin")
				checkin_doc.employee = employee_id
				checkin_doc.employee_name = entry['employee_name'][:140]
				checkin_doc.device_id = entry['device_id']
				checkin_doc.time = entry['Checkin_time']
				checkin_doc.shift = entry['shift']

				if i == 0:  # First entry of the day
					checkin_doc.log_type = 'IN'
					last_log_type = 'IN'
					
				elif i == len(entries) - 1:  # Last entry of the day
					if last_log_type == 'IN':
						checkin_doc.log_type = 'OUT'
						
					else:
						checkin_doc.log_type = 'IN'
						
				else:  # Intermediate entries
					if last_log_type == 'IN':
						checkin_doc.log_type = 'OUT'
						last_log_type = 'OUT'
						# print("ous else if out",checkin_doc.log_type)
					else:
						checkin_doc.log_type = 'IN'
						# print("out else else innnn",checkin_doc.log_type)
						last_log_type = 'IN'
					
				try:
					# if not frappe.db.exists("Employee Checkin", {"employee": employee_id, "time": entry['Checkin_time']}):
					checkin_doc.insert(ignore_permissions=True)
					# print("-----",checkin_doc)
					employee_checkins.append(checkin_doc)
					
				except Exception as e:
					frappe.msgprint(f"Error inserting Employee Checkin: {str(e)}")

	return employee_checkins




