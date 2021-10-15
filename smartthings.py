#My Secrets
from my_secrets.secrets import ST_WEBHOOK, PA_TOKEN

#HTTP Libs
import requests

#JSON Libs
import json

#sqlite3 Libs
import sqlite3

#os Libs
from os.path import exists

#datetime Libs
from datetime import datetime

HOME_URL = 'https://api.smartthings.com/v1/'
APP_HEADERS = {'Authorization': 'Bearer ' + PA_TOKEN}  # Use this header when you don't have an authToken being passed in

STDB = '/home/pi/smartthings/smartthings.db'  #Path to SmartThings DB - It's best to use the full path.

# This is the list of supported capabilities and attributes.  Add to this list as you add more support.  This helps keep your JSON payload smaller.
DEV_LIST = [('presenceSensor', 'presence'), ('battery', 'battery'), ('switch', 'switch'), ('switchLevel', 'level'),
	('doorControl', 'door'), ('lock', 'lock'), ('temperatureMeasurement', 'temperature'),
	('relativeHumidityMeasurement', 'humidity'), ('contactSensor', 'contact'), ('motionSensor', 'motion'),
	('thermostatCoolingSetpoint', 'coolingSetpoint'), ('thermostatOperatingState', 'thermostatOperatingState'),
	('thermostatFanMode', 'thermostatFanMode'), ('thermostatHeatingSetpoint', 'heatingSetpoint'), ('thermostatMode', 'thermostatMode')]

# This just gives us a list of supported capabilities (the first item in each tuple in DEV_LIST) that we can use to test against later
CAP_LIST = [cap[0] for cap in DEV_LIST]

class SmartThings:

	def __init__(self, location_id=''): #Pass a location_id if you have multiple locations
		self.location_id = location_id
		self.app_id = ''
		self.installed_app_id = ''
		self.app_name = ''
		self.configuration_id = ''
		self.name = ''
		self.location = {'location': {'locationId' : '', 'name' : ''}, 'presence':[], 'rooms' : [], 'scenes': []}

	def initialize(self, refresh=True):
		#  This creates and seeds the database, if needed, and updates the database with device status
		#  and builds out the self.location JSON structure with the data to pass to our HTML.
		if not self.location_id:
			self.getInstalledApps()
		if not exists(STDB):
			self.createDB()
			self.loadData()
		self.readData(refresh)

	def getInstalledApps(self):
		#If you only have one location, this will read by AppID to get the installed location_id for you.
		fullURL = HOME_URL + 'installedapps?appid=' + ST_WEBHOOK
		headers = APP_HEADERS
		r = requests.get(fullURL, headers=headers)
		print('Get Installed Apps: %d' % r.status_code)
		if r.status_code == 200:
			data = json.loads(r.text)
			self.location_id = data['items'][0]['locationId']

	def createDB(self):
		# Create our smartthings.db
		conn = sqlite3.connect(STDB)
		cursor = conn.cursor()

		create_location_table = '''CREATE TABLE IF NOT EXISTS location(
			location_id TEXT NOT NULL PRIMARY KEY,
			name TEXT NOT NULL,
			nickname TEXT UNIQUE NOT NULL,
			latitude TEXT,
			longitude TEXT,
			time_zone_id TEXT,
			email TEXT
			)'''
		cursor.execute(create_location_table)

		create_app_table = '''CREATE TABLE IF NOT EXISTS app(
			location_id TEXT NOT NULL,
			app_id TEXT NOT NULL,
			installed_app_id TEXT,
			display_name TEXT,
			configuration_id TEXT,
			PRIMARY KEY (location_id, app_id),
			FOREIGN KEY (location_id)
			REFERENCES location (location_id)
			ON DELETE CASCADE
			ON UPDATE CASCADE
			)'''
		cursor.execute(create_app_table)

		create_scene_table = '''CREATE TABLE IF NOT EXISTS scene(
			scene_id TEXT NOT NULL PRIMARY KEY,
			name TEXT NOT NULL,
			location_id TEXT NOT NULL,
			visible INTEGER,
			seq INTEGER,
			guest_access INTEGER,
			FOREIGN KEY (location_id)
			REFERENCES location (location_id)
			ON DELETE CASCADE
			ON UPDATE CASCADE
			)'''
		cursor.execute(create_scene_table)

		create_room_table = '''CREATE TABLE IF NOT EXISTS room(
			location_id TEXT NOT NULL,
			room_id TEXT NOT NULL,
			name TEXT NOT NULL,
			visible INTEGER,
			seq INTEGER,
			guest_access INTEGER,
			PRIMARY KEY (room_id)
			FOREIGN KEY (location_id)
			REFERENCES location (location_id)
			ON DELETE CASCADE
			ON UPDATE CASCADE
			)'''
		cursor.execute(create_room_table)

		create_device_table = '''CREATE TABLE IF NOT EXISTS device(
			location_id TEXT NOT NULL,
			room_id TEXT NOT NULL,
			device_id TEXT NOT NULL,
			presentation_id TEXT,
			name TEXT,
			health TEXT,
			label TEXT,
			category TEXT,
			device_type_name TEXT,
			visible INTEGER,
			seq INTEGER,
			guest_access INTEGER,
			nickname TEXT,
			icon TEXT,
			PRIMARY KEY (device_id),
			FOREIGN KEY (room_id)
			REFERENCES room (room_id)
			ON DELETE CASCADE
			ON UPDATE CASCADE
			)'''
		cursor.execute(create_device_table)

		create_capability_table = '''CREATE TABLE IF NOT EXISTS capability(
			location_id TEXT NOT NULL,
			device_id TEXT NOT NULL,
			capability_id TEXT NOT NULL,
			visible INTEGER,
			state TEXT,
			seq INTEGER,
			updated TEXT,
			PRIMARY KEY (device_id, capability_id),
			FOREIGN KEY (device_id)
			REFERENCES device (device_id)
			ON DELETE CASCADE
			ON UPDATE CASCADE
			)'''
		cursor.execute(create_capability_table)

		conn.commit()
		conn.close()

	def loadData(self):
		# Load seed data into the database
		status = False
		if self.loadLocation():
			if self.loadAppConfig():
				if self.loadRooms():
					if self.loadDevices():
						print('Data Loaded...')
						status = True
					else:
						print('Failed loading devices.')
				else:
					print('Failed loading rooms.')
			else:
				print('Failed loading App Config.')
		else:
			print(f'Failed loading location ({self.location_id}).')
		return status
		

	def readData(self, refresh=True):
		# Update device status/health and scenes and build the self.location JSON for the browser
		status = False
		if self.readLocation():
			if self.readAppConfig():
				if self.readRooms():
					if self.readDevices():
						if refresh:
							if self.loadAllDevicesStatus():
								if self.loadAllDevicesHealth():
									if self.loadAllScenes():
										status = True
									else:
										print('Failed loading scenes.')
								else:
									print('Failed loading All Devices Health.')
							else:
								print('Failed loading All Devices Status.')
						if self.readAllScenes():
							print('Data Read...')
							status = True
						else:
							print('Failed reading scenes.')
					else:
						print('Failed reading devices.')
				else:
					print('Failed reading rooms.')
			else:
				print('Failed reading App Config.')
		else:
			print(f'Failed reading location ({self.location_id}).')
		#print(self.location)
		return status

	def loadLocation(self):
		#This will give you all of the location related data and populate the database.
		status = False
		fullURL = HOME_URL + 'locations/' + self.location_id
		headers = APP_HEADERS
		r = requests.get(fullURL, headers=headers)
		print('Get Location: %d' % r.status_code)
		if r.status_code == 200:
			data = json.loads(r.text)
			conn = sqlite3.connect(STDB)
			cursor = conn.cursor()
			update_location = 'update location set name=?, latitude=?, longitude=?, time_zone_id=? where location_id=?'
			update_values = (data['name'], data['latitude'], data['longitude'], data['timeZoneId'], self.location_id)
			cursor.execute(update_location, update_values)
			if cursor.rowcount == 0:
				insert_location = 'insert into location (location_id, name, nickname, latitude, longitude, time_zone_id, email) values(?,?,?,?,?,?,?)'
				insert_values = (self.location_id, data['name'], '', data['latitude'], data['longitude'], data['timeZoneId'], '')
				cursor.execute(insert_location, insert_values)
			conn.commit()
			conn.close()
			status = True
		return status

	def readLocation(self):
		#This will read location data from the database and populate self.location
		status = False
		conn = sqlite3.connect(STDB)
		cursor = conn.cursor()
		for row in cursor.execute('select * from location where location_id=?', (self.location_id,)):
			location_id, name, nickname, latitude, longitude, time_zone, email = row
			self.name = name
			self.display_name = nickname if len(nickname) > 0 else name
			self.latitude = latitude
			self.longitude = longitude
			self.location = {'location': {'locationId' : location_id, 'name' : self.display_name, 'latitude' : latitude, 'longitude' : longitude, 'timeZoneId' : time_zone, 'email' : email}, 'presence':[], 'rooms' : []}
			status = True
		conn.close()
		return status

	def loadAppConfig(self):
		#This tree will give you all of the information about your app, including the installedAppId, displayName, description, configurationId,
		#  and all configuration data.
		#  If you're only interested in the devices selected during user install/update, you can get all of that info here.
		status = False
		fullURL = HOME_URL + 'installedapps?locationId=' + self.location_id + '&appId=' + ST_WEBHOOK
		headers = APP_HEADERS
		r = requests.get(fullURL, headers=headers)
		print('Get installedAppId: %d' % r.status_code)
		if r.status_code == 200:
			print('Config - App *****************************************\n')
			#print(r.text)
			listData = json.loads(r.text)
			installedAppId = ''
			displayName = ''
			configurationId = ''
			for item in listData['items']:
				if item['appId'] == ST_WEBHOOK and item['installedAppStatus'] == 'AUTHORIZED':
					installedAppId = item['installedAppId']
					displayName = item['displayName']
					self.installed_app_id = installedAppId
			baseURL = HOME_URL + 'installedapps/' + installedAppId
			endURL = '/configs'
			headers = APP_HEADERS
			fullURL = baseURL + endURL
			r = requests.get(fullURL, headers=headers)
			print('Get configurationId: %d' % r.status_code)
			if r.status_code == 200:
				print('Config ID *****************************************\n')
				#print(r.text)
				appData = json.loads(r.text)
				conn = sqlite3.connect(STDB)
				cursor = conn.cursor()
				for item in appData['items']:
					if item['configurationStatus'] == 'AUTHORIZED':
						configurationId = item['configurationId']
						insert_app = 'insert or replace into app values(?,?,?,?,?)'
						app_values = (self.location_id, ST_WEBHOOK, installedAppId, displayName, configurationId)
						cursor.execute(insert_app, app_values)
						conn.commit()
						self.app_name = displayName
						self.configuration_id = configurationId
						fullURL = fullURL + '/' + configurationId
						r = requests.get(fullURL, headers=headers)
						print('Get appConfig: %d' % r.status_code)
						if r.status_code == 200:
							status = True
							print('Config Data *****************************************\n')
							print(r.text)
		conn.close()
		return status

	def readAppConfig(self):
		status = False
		conn = sqlite3.connect(STDB)
		cursor = conn.cursor()
		for row in cursor.execute('select installed_app_id, display_name from app where app_id=? and location_id=?', (ST_WEBHOOK, self.location_id)):
			self.installed_app_id =row[0]
			self.app_name = row[1]
			status = True
		conn.close()
		return status

	def loadRooms(self):
		#This will return all rooms at this location and populate the database.
		status = False
		baseURL = HOME_URL + 'locations/'
		endURL = '/rooms'
		headers = APP_HEADERS
		fullURL = baseURL + self.location_id + endURL
		r = requests.get(fullURL, headers=headers)
		print('Get Rooms: %d' % r.status_code)
		if r.status_code == 200:
			data = json.loads(r.text)
			conn = sqlite3.connect(STDB)
			cursor = conn.cursor()
			roomRows = []
			for row in cursor.execute('select room_id from room where location_id=?', (self.location_id,)):
				roomRows.append(row[0])
			update_room = 'update room set name=? where room_id=?'
			insert_room = 'insert into room (location_id, room_id, name, visible, seq) values(?,?,?,?,?)'
			for rm in data['items']:
				update_values = (rm['name'], rm['roomId'])
				cursor.execute(update_room, update_values)
				if cursor.rowcount == 1:
					roomRows.remove(rm['roomId'])
				else:
					insert_values = (self.location_id, rm['roomId'], rm['name'], 1, 99)
					cursor.execute(insert_room, insert_values)
				conn.commit()
			for roomId in roomRows:
				cursor.execute('update room set visible=? where room_id=?', (0, roomId))
				conn.commit()
			conn.close()
			status = True
		else:
			print('Get Rooms Failed.  Status: %s' % r.status_cd)
		return status

	def readRooms(self):
		#Load all room data from the database.
		status = False
		conn = sqlite3.connect(STDB)
		cursor = conn.cursor()

		self.location['rooms'] = []
		
		for row in cursor.execute('select * from room where location_id=? and visible=?', (self.location_id,1)):
			location_id, room_id, name, visible_val, seq, guest_access = row
			room = {'roomId' : room_id, 'name' : name, 'seq': seq, 'guest_access': guest_access, 'devices' : []}
			self.location['rooms'].append(room)
			status = True
		conn.close()
		return status

	def loadDevices(self):
		#This will give us all devices at this location, but we have to put them into room groupings or 
		#  presenceSensor groupings.  Stores the data in the database.
		status = False
		baseURL = HOME_URL + 'devices'
		endURL = '?locationId=' + self.location_id
		headers = APP_HEADERS
		fullURL = baseURL + endURL
		r = requests.get(fullURL, headers=headers)
		print('Get Devices: %d' % r.status_code)
		if r.status_code == 200:
			data = json.loads(r.text)
			conn = sqlite3.connect(STDB)
			cursor = conn.cursor()
			deviceRows = []
			for row in cursor.execute('select device_id from device where location_id=?', (self.location_id,)):
				deviceRows.append(row[0])
			update_device = 'update device set room_id=?, name=?, label=?, category=?, device_type_name=? where device_id=?'
			insert_device = 'insert into device (location_id,room_id,device_id,presentation_id,name,health,label,category,device_type_name,visible,seq,guest_access,nickname,icon) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
			insert_capability = 'insert into capability (location_id, device_id, capability_id, visible, state, seq, updated) values(?,?,?,?,?,?,?)'
			for dev in data['items']:
				dtn = dev.get('dth','')
				if dtn:
					dtn = dtn.get('deviceTypeName', '')
				update_device_values = (dev.get('roomId', 0), dev['name'], dev['label'], dev['components'][0]['categories'][0]['name'], dtn, dev['deviceId'])
				cursor.execute(update_device, update_device_values)
				if cursor.rowcount == 1:
					deviceRows.remove(dev['deviceId'])
				else:
					device_insert_values = (self.location_id, dev.get('roomId', 0), dev['deviceId'], dev.get('presentationId',''), dev['name'], '?', dev['label'], dev['components'][0]['categories'][0]['name'], dtn, 1, 99, 0, '', '')
					cursor.execute(insert_device, device_insert_values)
					for comp in dev['components']:
						for cap in comp['capabilities']:
							capability_values = (self.location_id, dev['deviceId'], cap['id'], 1, '', 99, '')
							cursor.execute(insert_capability, capability_values)
				status = True
				conn.commit()
			for deviceId in deviceRows:
				cursor.execute('update device set visible=? where device_id=?', (0, deviceId))
				conn.commit()
			conn.close()
		return status

	def readDevices(self):
		# Reads device data from the database.
		status = False
		conn = sqlite3.connect(STDB)
		cursor = conn.cursor()
		c2 = conn.cursor()
		self.location['presence'] = []
		for room in self.location['rooms']:
			room['devices'] = []
		for row in cursor.execute('select * from device where location_id=? and visible=?', (self.location_id,1)):
			d_location_id, d_room_id, d_device_id, d_presentation_id, d_name, d_health, d_label, d_category, d_device_type, d_visible, d_seq, d_guest_access, d_nickname, d_icon = row
			device = {'deviceId' : d_device_id, 'name' : d_name, 'label' : d_nickname if d_nickname else d_label, 'seq': d_seq, 'health': d_health, 
				'guest_access': d_guest_access, 'icon': d_icon, 'capabilities' : []}
			for r2 in c2.execute('select * from capability where device_id=? and visible=?', (d_device_id, 1)):
				status = True
				c_location_id, c_device_id, c_capability_id, c_visible, c_state, c_seq, dt = r2
				if c_capability_id in CAP_LIST:
					capability = {'id' : c_capability_id, 'state' : c_state, 'seq': c_seq, 'updated': dt}
					device['capabilities'].append(capability)
			if len(device['capabilities']) > 0 and (d_room_id == 0 or d_room_id == '0'):
				self.location['presence'].append(device)
			else:
				if len(device['capabilities']) > 0:
					for room in self.location['rooms']:
						if room['roomId'] == d_room_id:
							room['devices'].append(device)

		conn.close()
		return status

	def loadAllDevicesStatus(self):
		#We spin through each device to get the current status of all of it's capabilities.
		#  This data gets written to the database and updates self.location.
		status = False
		baseURL = HOME_URL + 'devices/'
		headers = APP_HEADERS
		endURL = '/status'

		conn = sqlite3.connect(STDB)
		c1 = conn.cursor()
		dt = datetime.now().strftime('%m/%d/%y %H:%M:%S')

		for pres in self.location['presence']:
			fullURL = baseURL + pres['deviceId'] + endURL
			r = requests.get(fullURL, headers=headers)
			if r.status_code == 200:
				print('Device Loaded: %s' % pres['label'])
				data = json.loads(r.text)

				main = dict(data.get('components','')).get('main','')
				if main:
					for dev in DEV_LIST:
						cap = dict(main.get(dev[0],'')).get(dev[1],'')
						if cap:
							for capability in pres['capabilities']:
								if capability['id'] == dev[0]:
									capability['state'] = cap['value']
									capability['updated'] = dt
									c1.execute('update capability set state=?, updated=? where device_id=? and capability_id=?', 
										(cap['value'], dt, pres['deviceId'], dev[0]))
									conn.commit()

		for room in self.location['rooms']:
			for device in room['devices']:
				fullURL = baseURL + device['deviceId'] + endURL
				r = requests.get(fullURL, headers=headers)
				if r.status_code == 200:
					print('Device Loaded: %s' % device['label'])
					data = json.loads(r.text)

					main = dict(data.get('components','')).get('main','')
					if main:
						for dev in DEV_LIST:
							cap = dict(main.get(dev[0],'')).get(dev[1],'')
							if cap:
								for capability in device['capabilities']:
									if capability['id'] == dev[0]:
										capability['state'] = cap['value']
										c1.execute('update capability set state=?, updated=? where device_id=? and capability_id=?', 
											(cap['value'], dt, device['deviceId'], dev[0]))
										conn.commit()
										status = True
		conn.close()
		return status

	def loadAllDevicesHealth(self):
		#Here we spin through all devices to get it's current health status (online/offline).
		#  This data gets written to the database and updates self.location.
		status = False
		baseURL = HOME_URL + 'devices/'
		headers = APP_HEADERS
		endURL = '/health'

		conn = sqlite3.connect(STDB)
		c1 = conn.cursor()

		for pres in self.location['presence']:
			deviceId = pres['deviceId']
			fullURL = baseURL + str(deviceId) + endURL
			r = requests.get(fullURL, headers=headers)
			if r.status_code == 200:
				status = True
				data = json.loads(r.text)
				print('Get Presence Health: %s - %s' % (data['state'], pres['label']))
				pres['health'] = data['state']
				c1.execute('update device set health=? where device_id=?', (data['state'], deviceId))
				conn.commit()

		for rm in self.location['rooms']:
			for dev in rm['devices']:
				deviceId = dev['deviceId']
				fullURL = baseURL + deviceId + endURL
				r = requests.get(fullURL, headers=headers)
				if r.status_code == 200:
					status = True
					data = json.loads(r.text)
					print('Get Device Health: %s - %s' % (data['state'], dev['label']))
					dev['health'] = data['state']
					c1.execute('update device set health=? where device_id=?', (data['state'], deviceId))
					conn.commit()
		conn.close()
		return status

	def updateDeviceHealth(self, deviceId, status):
		#This gets called when a device health event fires.
		#  It updates the database and self.location.
		conn = sqlite3.connect(STDB)
		c1 = conn.cursor()
		
		for pres in self.location['presence']:
			for dev in pres['devices']:
				if dev['deviceId'] == deviceId:
					dev['health'] = status
					c1.execute('update device set health=? where device_id=?', (status, deviceId))
					conn.commit()
					conn.close()
					return True

		for room in self.location['rooms']:
			for dev in room['devices']:
				if dev['deviceId'] == deviceId:
					dev['health'] = status
					c1.execute('update device set health=? where device_id=?', (status, deviceId))
					conn.commit()
					conn.close()
					return True
		return False


	def loadAllScenes(self):
		#This will load all scenes and must be filtered for the location and writes them to the database.
		status = False
		baseURL = HOME_URL + 'scenes'
		headers = APP_HEADERS
		fullURL = baseURL
		r = requests.get(fullURL, headers=headers)
		
		conn = sqlite3.connect(STDB)
		c1 = conn.cursor()
		
		print(f'loadAllScenes() r.status_code: {r.status_code}')
		if r.status_code == 200:
			status = True
			data = json.loads(r.text)
			#print(f'*****Scenes\nr.text\n******')
			self.location['scenes'] = []
			sceneRows = []
			for row in c1.execute('select scene_id from scene where location_id=?', (self.location_id,)):
				sceneRows.append(row[0])
			print('Starting sceneRows: %s' % sceneRows)
			for scene in data['items']:
				if scene['locationId'] == self.location_id:
					scene_data = {'sceneId': scene['sceneId'], 'sceneName': scene['sceneName']}
					self.location['scenes'].append(scene_data)

					c1.execute('update scene set name=? where scene_id=?', (scene['sceneName'], scene['sceneId']))
					if c1.rowcount == 0:
						c1.execute('insert into scene (scene_id,name,location_id,visible,seq) values (?,?,?,?,?)',
						(scene['sceneId'], scene['sceneName'], self.location_id, 1, 99))
					else:
						sceneRows.remove(scene['sceneId'])
					# ~ c1.execute('insert or replace into scene values (?,?,?,?,?)', 
						# ~ (scene['sceneId'], scene['sceneName'], self.location_id, 1, 99))
					conn.commit()
			print('Ending sceneRows: %s' % sceneRows)
			for sceneId in sceneRows:
				c1.execute('delete from scene where scene_id=?', (sceneId,))
				conn.commit()
		conn.close()
		return status

	def readAllScenes(self):
		#Reads scenes from the database.
		status = False

		conn = sqlite3.connect(STDB)
		conn.row_factory = sqlite3.Row
		c1 = conn.cursor()
		self.location['scenes'] = []
		for scene in c1.execute('select * from scene where location_id=? and visible=?', (self.location_id,1)):
			self.location['scenes'].append(dict(scene))
			status = True
		return status

	def updateDevice(self, deviceId, capability, attribute, value):
		#This is called when a device event occurs.  It updates the database and self.location data 
		#  and then returns the values to be emitted to the browsers.
		print('Updating: %s / %s / %s / %s' % (deviceId, capability, attribute, value))

		emit_data = True
		emit_val = ()
		
		conn = sqlite3.connect(STDB)
		c1 = conn.cursor()
		dt = datetime.now().strftime('%m/%d/%y %H:%M:%S')

		if capability == 'presenceSensor':
			for pres in self.location['presence']:
				if pres['deviceId'] == deviceId:
					for cap in pres['capabilities']:
						if cap['id'] == capability:
							cap['state'] = value

							c1.execute('update capability set state=?, updated=? where device_id=? and capability_id=?',
								(value, dt, deviceId, capability))
								
							conn.commit()
							print(self.location['presence'])
							dev_json = json.dumps({'deviceId': deviceId,'capability': capability, 'value': value})
							emit_val = ('presence_chg', dev_json)
		else:
			for rm in self.location['rooms']:
				for dev in rm['devices']:
					if dev['deviceId'] == deviceId:
						for cap in dev['capabilities']:
							if cap['id'] == capability:
								if cap['state'] == value:
									emit_data = False
								cap['state'] = value
								if emit_data:
									
									c1.execute('update capability set state=?, updated=? where device_id=? and capability_id=?',
										(value, dt, deviceId, capability))
										
									conn.commit()									
									dev_json = json.dumps({'deviceId': deviceId,'capability': capability, 'value': value})
									emit_val = ('device_chg', dev_json)
		conn.close()
		return emit_val

	def deleteSubscriptions(self, authToken, appID):
		#Deletes all subscriptions.
		baseURL = HOME_URL + 'installedapps/'
		headers = {'Authorization': 'Bearer ' + authToken}
		endURL = '/subscriptions'

		r = requests.delete(baseURL + str(appID) + endURL, headers=headers)

		if r.status_code == 200:
			return True

		return False

	def deviceHealthSubscriptions(self, authToken, locationID, appID):
		#Subscribes to device health changes.
		baseURL = HOME_URL + 'installedapps/'
		headers = {'Authorization': 'Bearer ' + authToken}
		endURL = '/subscriptions'
		fullURL = baseURL + str(appID) + endURL

		datasub = {
			'sourceType':'DEVICE_HEALTH',
			'deviceHealth': {
				'locationId':locationID,
				'subscriptionName':'deviceHealthSubscription'
				}
			}
		r = requests.post(fullURL, headers=headers, json=datasub)
		print('Device Health Subscription: %d' % r.status_code)
		if r.status_code == 200:
			return True

		return False

	def capabilitySubscriptions(self, authToken, locationID, appID, capability, attribute, subName, stateChangeOnly=True):
		#Subscribes to specific capability status changes.
		baseURL = HOME_URL + 'installedapps/'
		headers = {'Authorization': 'Bearer ' + authToken}
		endURL = '/subscriptions'
		fullURL = baseURL + str(appID) + endURL

		datasub = {
			'sourceType':'CAPABILITY',
			'capability': {
				'locationId':locationID,
				'capability':capability,
				'attribute':attribute,
				'value':'*',
				'stateChangeOnly':stateChangeOnly,
				'subscriptionName':subName
				}
			}
		r = requests.post(fullURL, headers=headers, json=datasub)
		print('Capability Subscription [%s / %s]: %d' % (capability, attribute, r.status_code))
		if r.status_code == 200:
			return True

		return False

	def deviceSubscriptions(self, authToken, appID, deviceID, capability, attribute, subName):
		#Subscribes to device-specific events.
		baseURL = HOME_URL + 'installedapps/'
		headers = {'Authorization': 'Bearer ' + authToken}
		endURL = '/subscriptions'
		fullURL = baseURL + str(appID) + endURL

		datasub = {
			'sourceType':'DEVICE',
			'device': {
				'deviceId':deviceID,
				'componentId':'*',
				'capability':capability,
				'attribute':'*',
				'value':'*',
				'stateChangeOnly':True,
				'subscriptionName':subName
				}
			}
		r = requests.post(fullURL, headers=headers, json=datasub)
		print('Device Subscription: %d' % r.status_code)
		if r.status_code == 200:
			return True

		return False

	def changeDevice(self, deviceId, capability, value, user=None):
		#This is called when a user requests to change a device state.
		#  It calls an API which, if successful, will trigger a subsequent device event.
		if user and user.role == 'Guest':
			conn = sqlite3.connect(STDB)
			c1 = conn.cursor()
			for row in c1.execute('select guest_access from device where device_id=?', (deviceId,)):
				print('device: %s' % row[0])
			conn.close()
			if not row[0] or row[0] != 1:
				print('Guest not allowed to run this device!')
				return False
		baseURL = HOME_URL + 'devices/'
		headers = APP_HEADERS
		endURL = '/commands'
		fullURL = baseURL + str(deviceId) + endURL
		if capability == 'switchLevel':
			datasub = {
				'commands': [ {
					'component':'main',
					'capability':capability,
					'command':'setLevel',
					'arguments': [
						int(value)
					]
				}
			  ]
			}
		else:
			datasub = {
				'commands': [ {
					'component':'main',
					'capability':capability,
					'command':value
					}
				]
			}
		r = requests.post(fullURL, headers=headers, json=datasub)
		print('Change Device: %d' % r.status_code)
		print (r.text)
		if r.status_code == 200:
			return True

		return False

	def changeThermostat(self, settings, user=None):
		#This is called when a user requests to change a thermostat.
		if user and user.role == 'Guest':
			conn = sqlite3.connect(STDB)
			c1 = conn.cursor()
			for row in c1.execute('select guest_access from device where device_id=?', (settings['deviceId'],)):
				print('device: %s' % row[0])
			conn.close()
			if not row[0] or row[0] != 1:
				print('Guest not allowed to change thermostat!')
				return False
		baseURL = HOME_URL + 'devices/'
		headers = APP_HEADERS
		endURL = '/commands'
		fullURL = baseURL + settings['deviceId'] + endURL

		commandsPayload = []
		for command in settings['commands']:
			arguments = []
			if command['capability'] == 'thermostatHeatingSetpoint':
				cmd = 'setHeatingSetpoint'
				arguments.append(int(command['value']))
			elif command['capability'] == 'thermostatCoolingSetpoint':
				cmd = 'setCoolingSetpoint'
				arguments.append(int(command['value']))
			else:
				cmd = command['value']
			commandsPayload.append({'component':'main', 'capability':command['capability'], 'command':cmd, 'arguments':arguments})

		datasub = {
			'commands': commandsPayload
		}
		print(datasub)
		
		r = requests.post(fullURL, headers=headers, json=datasub)
		print('Change Thermostat: %d' % r.status_code)
		print (r.text)
		if r.status_code == 200:
			return True

		return False

	def runScene(self, scene_id, user=None):
		# Execute a scene
		print(f'Running scene: {scene_id}')
		if user and user.role == 'Guest': # If user is a Guest, make sure they have access first
			conn = sqlite3.connect(STDB)
			c1 = conn.cursor()
			for row in c1.execute('select guest_access from scene where scene_id=?', (scene_id,)):
				print('scene: %s' % row[0])
			conn.close()
			if not row[0] or row[0] != 1:
				print('Guest not allowed to run this scene!')
				return False
		fullURL = HOME_URL + 'scenes/' + scene_id + '/execute'
		headers = APP_HEADERS
		r = requests.post(fullURL, headers=headers)
		print(f'r.status_code: {r.status_code}')
		if (r.status_code == 200):
			return True
		return False

	def getConfig(self):
		# Get Location and Room-Level configs.  Used by Admin console.
		config = {'location': {}, 'rooms': []}
					
		conn = sqlite3.connect(STDB)
		c1 = conn.cursor()
		c2 = conn.cursor()
		c3 = conn.cursor()
		
		for loc in c1.execute('select location_id, name, nickname, email from location where location_id=?', (self.location_id,)):
			newLocation = {'location_id': loc[0], 'name': loc[1], 'nickname': loc[2], 'email': loc[3]}
		config['location'] = newLocation
		
		for rm in c1.execute('select room_id, name, seq, visible, guest_access from room where location_id=?', (self.location_id,)):
			newRoom = {'room_id': rm[0], 'name': rm[1], 'seq': rm[2], 'visible': rm[3], 'guest_access': 0 if not rm[4] else rm[4], 'devices': []}
			for dev in c2.execute('select device_id, label, seq, visible, guest_access, icon from device where room_id=?', (rm[0],)):
				newDevice = {'device_id': dev[0], 'label': dev[1], 'seq': dev[2], 'visible': dev[3], 'guest_access': 0 if not dev[4] else dev[4], 'icon': dev[5] if dev[5] else '', 'capabilities': []}
				for cap in c3.execute('select capability_id, seq, visible from capability where device_id=?', (dev[0],)):
					if cap[0] in CAP_LIST:
						newCapability = {'capability_id': cap[0], 'seq': cap[1], 'visible': cap[2]}
						newDevice['capabilities'].append(newCapability)
				if len(newDevice['capabilities']) > 0:
					newRoom['devices'].append(newDevice)
			if len(newRoom['devices']) > 0:
				config['rooms'].append(newRoom)
		conn.close()
		return config
		
	def updateConfigs(self, configData):
		# Update location and room configs.
		status = False
		conn = sqlite3.connect(STDB)
		c1 = conn.cursor()
		location_id = ''
		nickname = ''
		email = ''
		if len(configData['location']) > 0:
			for item in configData['location']:
				if item.get('location_id', ''):
					location_id = item['location_id']
				elif item.get('nickname',''):
					nickname = item['nickname']
				elif item.get('email',''):
					email = item['email']
			print('nickname: %s / email: %s' % (nickname, email))
			c1.execute('update location set nickname=?, email=? where location_id=?', (nickname, email, location_id))
			status = True
		print('Room items: %d' % len(configData['rooms']))
		for room in configData['rooms']:
			print(room)
			room_id = room.get('room_id', '')
			seq = room.get('seq', 99)
			visible = room.get('visible', 1)
			guest_access = room.get('guest_access', 0)
			c1.execute('update room set seq=?, visible=?, guest_access=? where room_id=?', (seq, visible, guest_access, room_id))
			status = True
		print('Device items: %d' % len(configData['devices']))
		for device in configData['devices']:
			print(device)
			device_id = device.get('device_id', '')
			seq = device.get('seq', 99)
			visible = device.get('visible', 1)
			guest_access = device.get('guest_access', 0)
			icon = device.get('icon', '')
			c1.execute('update device set seq=?, visible=?, guest_access=?, icon=? where device_id=?', (seq, visible, guest_access, icon, device_id))
			status = True
		print('Capability items: %d' % len(configData['capabilities']))
		for capability in configData['capabilities']:
			print(capability)
			device_id = capability.get('device_id', '')
			capability_id = capability.get('capability_id', '')
			seq = capability.get('seq', 99)
			visible = capability.get('visible', 1)
			print(f'seq={seq}, visible={visible}, device_id={device_id}, capability_id={capability_id}')
			c1.execute('update capability set seq=?, visible=? where device_id=? and capability_id=?', (seq, visible, device_id, capability_id))
			status = True
		conn.commit()
		conn.close()
		return status
		
	def getPresence(self):
		# Get Presence configs.  Used by Admin console.
		config = {'presence': []}
		
		conn = sqlite3.connect(STDB)
		conn.row_factory = sqlite3.Row
		c1 = conn.cursor()

		for sensor in c1.execute('select device_id, label, seq, visible, nickname from device where location_id=? and category=?', (self.location_id, 'MobilePresence')):
			config['presence'].append(dict(sensor))
		conn.close()
		return config
		
	def updatePresenceConfigs(self, configData):
		# Update Presence configs.
		status = False
		conn = sqlite3.connect(STDB)
		c1 = conn.cursor()
		if len(configData['presence']) > 0:
			for sensor in configData['presence']:
				print(f'Updating {sensor["device_id"]}')
				c1.execute('update device set nickname=?, seq=?, visible=? where device_id=?', 
					(sensor['nickname'], sensor['seq'], sensor['visible'], sensor['device_id']))
				status = True
			conn.commit()
		conn.close()
		return status
	
	def getScenes(self):
		# Get Scene-level configs.  Used by Admin console.
		config = {'scenes': []}
		
		conn = sqlite3.connect(STDB)
		conn.row_factory = sqlite3.Row
		c1 = conn.cursor()
		
		for scene in c1.execute('select * from scene where location_id=?', (self.location_id,)):
			sceneRecord = dict(scene)
			if sceneRecord['guest_access'] is None:
				sceneRecord['guest_access'] = 0
			config['scenes'].append(sceneRecord)
		return config
		
	def updateSceneConfigs(self, configData):
		# Update scene configs.
		status = False
		conn = sqlite3.connect(STDB)
		c1 = conn.cursor()
		if len(configData['scenes']) > 0:
			for scene in configData['scenes']:
				print(f'Updating {scene["scene_id"]}: visible: {scene["visible"]}')
				c1.execute('update scene set seq=?, visible=?, guest_access=? where scene_id=?', 
					(scene['seq'], scene['visible'], scene['guest_access'], scene['scene_id']))
				status = True
			conn.commit()
		conn.close()
		return status


if __name__ == '__main__': #This will only be True if we are directly running this file for testing.
	st = SmartThings()

	#  If multiple locations associated with account, use this instead #
	#
	#location_id = 'xxxxxxxxxxxxxxxx' # copy value from incoming request
	#st = SmartThings(location_id)

	st.initialize()
	print('*******************************\n\n')
	print(st.location)
