import time
import gc
import board
import displayio
import digitalio
import terminalio
import busio
import neopixel
import adafruit_requests as requests
from adafruit_esp32spi import adafruit_esp32spi_socket as socket
from adafruit_esp32spi import adafruit_esp32spi
from adafruit_esp32spi import adafruit_esp32spi_wifimanager
from adafruit_display_text import label

try:
    from secrets import secrets
except ImportError:
    print("Wifi and API secrets are kept in secrets.py, please add them there!")
    raise

class PyGlancePortal:
    def __init__(self, debug=False):
        self._settings = {
            "ssid": secrets["ssid"],
            "password": secrets["password"],
            "timezone": secrets["timezone"],
            "aio_username": secrets["aio_username"],
            "aio_key": secrets["aio_key"],
            "pirateweather_api_key": secrets["pirateweather_api_key"],
            "pirateweather_api_forecast": secrets["pirateweather_api_forecast"],
            "twitch_api_key": secrets["twitch_api_key"],
            "twitch_api_secret": secrets["twitch_api_secret"],
            "twitch_api_streamers": secrets["twitch_api_streamers"],
            "sports_leagues": secrets["sports_leagues"],
            "sports_api_nhl": secrets["sports_api_nhl"],
            "sports_api_nhl_teams": secrets["sports_api_nhl_teams"],
            "sports_api_nfl": secrets["sports_api_nfl"],
            "sports_api_nfl_teams": secrets["sports_api_nfl_teams"],
            "sports_api_mlb": secrets["sports_api_mlb"],
            "sports_api_mlb_teams": secrets["sports_api_mlb_teams"],
            "sports_api_prem": secrets["sports_api_prem"],
            "sports_api_prem_teams": secrets["sports_api_prem_teams"],
            "sports_api_mls": secrets["sports_api_mls"],
            "sports_api_mls_teams": secrets["sports_api_mls_teams"],
            "default_weather_icon": "/icons/weather/unknown.bmp",
            "default_twitch_icon": "/icons/streamers/twitch.bmp"
        }

        self._debug = debug
        self._debug_refresh_counter = 0
        self._debug_error_counter = 0
        self._debug_total_error_counter = 0
        self._debug_reset_counter = 0
        self._debug_total_reset_counter = 0
        self._debug_wifi_retry_counter = 0

        self._today = 0
        self._updated = ""
        self._twitch_bearer_token = ""
        self._display_groups = {}
        self.reset_display_groups()

        # PyPortal Board Setup
        board.DISPLAY.brightness = 1
        self._status_light = neopixel.NeoPixel(board.NEOPIXEL, 1, brightness=0.2)
        self._led = digitalio.DigitalInOut(board.D13)
        self._led.direction = digitalio.Direction.OUTPUT

        # PyPortal ESP32 Setup
        self._esp32_cs = digitalio.DigitalInOut(board.ESP_CS)
        self._esp32_ready = digitalio.DigitalInOut(board.ESP_BUSY)
        self._esp32_reset = digitalio.DigitalInOut(board.ESP_RESET)
        self._spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
        self._esp = None

        self._wifi_client = None
        self._socket = None
        self._requests = None

        self.connect_wifi()

    def connect_wifi(self):
        # ESP32 Setup
        self._esp = adafruit_esp32spi.ESP_SPIcontrol(self._spi, self._esp32_cs, self._esp32_ready, self._esp32_reset)

        if self._esp.status == adafruit_esp32spi.WL_IDLE_STATUS:
            print("ESP32 found and in idle mode")
        print("Firmware vers.", self._esp.firmware_version)
        print("MAC addr:", [hex(i) for i in self._esp.MAC_address])

        # WiFi Setup
        if self._debug:
            print("Visible SSIDs:")
            for ap in self._esp.scan_networks():
                print("%s  RSSI: %d" % (str(ap["ssid"], "utf-8"), ap["rssi"]))


        self._debug_wifi_retry_counter = 0
        print("Connecting configured WiFi...")
        while not self._esp.is_connected:
            self._debug_wifi_retry_counter += 1
            try:
                self._esp.connect_AP(self._settings["ssid"], self._settings["password"])
            except (RuntimeError, ConnectionError) as e:
                # Defensive exception handling for ConnectionError: Failed to request hostname
                if self._debug_wifi_retry_counter > 1:
                    board.DISPLAY.root_group = displayio.CIRCUITPYTHON_TERMINAL
                print("Could not connect to WiFi, retrying:\n", e)
                time.sleep(5)
                continue

        print("Connected to:", str(self._esp.ssid, "utf-8"), "  RSSI:", self._esp.rssi)
        print("IP address:", self._esp.pretty_ip(self._esp.ip_address))

        requests.set_socket(socket, self._esp)

    def get_dayname(self, wday_num):
        days = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"]
        return(days[wday_num%7])

    def fetch_datetime(self):
        url = "https://io.adafruit.com/api/v2/{aio_username}/integrations/time/struct.json?tz=" + self._settings["timezone"]
        r = requests.get(url.format(aio_username=self._settings["aio_username"]), headers={"X-AIO-KEY":self._settings["aio_key"]})
        t = r.json()
        return time.struct_time((t["year"], t["mon"], t["mday"], t["hour"], t["min"], t["sec"], t["wday"], t["yday"], t["isdst"]))

    def fetch_forecast(self):
        url = self._settings["pirateweather_api_forecast"]
        r = requests.get(url.format(pirateweather_api_key=self._settings["pirateweather_api_key"]))
        return self.parse_forecast(r.json())

    def fetch_twitch_bearer_token(self):
        expires = 0
        if self._twitch_bearer_token != "":
            exp = requests.get("https://id.twitch.tv/oauth2/validate", headers={"Authorization":"OAuth "+self._twitch_bearer_token})
            expires = exp.json()["expires_in"]
            print("Twitch bearer token expires in " + str(expires))
        if self._twitch_bearer_token == "" or expires < 864000: # Refresh token if less than 1 week until expiry
            print("Fetching new Twitch bearer token")
            url = "https://id.twitch.tv/oauth2/token?client_id={client_id}&client_secret={client_secret}&grant_type=client_credentials"
            r = requests.post(url.format(client_id=self._settings["twitch_api_key"], client_secret=self._settings["twitch_api_secret"]))
            self._twitch_bearer_token = r.json()["access_token"]
        return self._twitch_bearer_token

    def fetch_twitch_streams(self):
        streamers = self._settings["twitch_api_streamers"].split(",")
        qsparam = "user_login="
        for idx,x in enumerate(streamers):
            streamers[idx] = qsparam + streamers[idx]
        t = self.fetch_twitch_bearer_token()
        r = requests.get("https://api.twitch.tv/helix/streams?" + "&".join(streamers), headers={"Client-ID":self._settings["twitch_api_key"],"Authorization":"Bearer "+t})
        return self.parse_twitch_streams(r.json())

    def fetch_league(self, league, teams, league_url, group, numlive):
        if len(teams) == 0:
            print("No teams for " + league + ". Skipping.")
            return numlive
        for idx,x in enumerate(teams.split(",")):
            if self._debug:
                print(idx, " ", league, " ", x)
            team_data = self.fetch_team(league_url, league, x)
            if len(team_data) > 0:
                team_icon = "/icons/sports/"+ team_data + ".bmp"
                if self._debug:
                    print(team_icon)
                try:
                    team_file = open(team_icon, "rb")
                except OSError as e:
                    team_file = open(self._settings["default_weather_icon"], "rb")
                img = displayio.OnDiskBitmap(team_file)
                img_sprite = displayio.TileGrid(img, pixel_shader=displayio.ColorConverter(), x=320-(34*(numlive+1)), y=2)
                group.append(img_sprite)
                numlive = numlive + 1
            elif self._debug:
                print("No game for " + league + " " + x)
        return numlive

    def fetch_team(self, api_url, league, team):
        r = requests.get(api_url+team)
        return self.parse_team(league, team, r.json())

    def parse_forecast(self, forecast_json):
        forecast_days = list()
        for x in range(0,6):
            day = forecast_json["daily"]["data"][x]
            forecast_days.append((day["icon"], int(round(day["temperatureLow"])), int(round(day["temperatureHigh"]))))
        return forecast_days

    def parse_twitch_streams(self, streams_json):
        streamers = list()
        if "data" in streams_json:
            for x in streams_json["data"]:
                if x["type"] == "live":
                    streamers.append(x["user_name"])
        return streamers

    def parse_team(self, league, team, team_json):
        t = ""
        if team_json["sports"][0]["leagues"][0]["events"][0]["status"] == "in":
            t = league + "/" + team
            if self._debug:
                print("game:" + team_json["sports"][0]["leagues"][0]["events"][0]["shortName"] + " status:" + team_json["sports"][0]["leagues"][0]["events"][0]["status"])
        return t

    def reset_display_groups(self):
        self._display_groups = {
            "weather_group": displayio.Group(),
            "days_group": displayio.Group(),
            "temp_group": displayio.Group(),
            "stream_group": displayio.Group(),
            "sports_group": displayio.Group(),
            "updated_group":  displayio.Group(),
            "memory_group": displayio.Group(),
            "error_group": displayio.Group()
        }

    def build_datetime(self):
        try:
            datetime = self.fetch_datetime()
            if self._debug:
                print(datetime)

            self._today = datetime.tm_wday
            formatted_min = "00"
            if datetime.tm_min < 10:
                formatted_min = "0" + str(datetime.tm_min)
            else:
                formatted_min = str(datetime.tm_min)

            self._updated = "u:" + str(datetime.tm_hour) + ":" + formatted_min
        except (ValueError, RuntimeError) as e:
            self._debug_error_counter += 1
            print("Failed to get time data\n", e)
            time.sleep(5)

    def build_weather(self):
        try:
            forecastdata = self.fetch_forecast()

            for idx,x in enumerate(forecastdata):
                if self._debug:
                    print(idx, " ", x[0], " ", str(x[1]), " ", str(x[2]))
                weather_icon = "/icons/weather/"+ x[0] + ".bmp"
                try:
                    icon_file = open(weather_icon, "rb")
                except OSError as e:
                    icon_file = open(self._settings["default_weather_icon"], "rb")
                icon = displayio.OnDiskBitmap(icon_file)
                icon_sprite = displayio.TileGrid(icon, pixel_shader=displayio.ColorConverter(), x=16+(idx*50), y=100)
                self._display_groups["weather_group"].append(icon_sprite)

                temp = "H:" + str(x[2]) + "\nL:" + str(x[1])
                temp_area = label.Label(terminalio.FONT, text=temp)
                temp_area.x = 22+(idx*50)
                temp_area.y = 150
                self._display_groups["temp_group"].append(temp_area)

                d = self.get_dayname(self._today+idx)
                day_area = label.Label(terminalio.FONT, text=d)
                day_area.x = 22+(idx*50)
                day_area.y = 90
                self._display_groups["days_group"].append(day_area)
        except (KeyError, ValueError, RuntimeError) as e:
            self._debug_error_counter += 1
            print("Failed to get forecast data\n", e)
            time.sleep(5)

    def build_sports(self):
        live_teams = 0
        leagues = self._settings["sports_leagues"].split(",")

        for idx,x in enumerate(leagues):
            try:
                current_league = x
                live_teams = self.fetch_league(current_league, self._settings["sports_api_" + x + "_teams"], self._settings["sports_api_" + x], self._display_groups["sports_group"], live_teams)
            except (KeyError, ValueError, RuntimeError) as e:
                self._debug_error_counter += 1
                print("Failed to get " + current_league + " data\n", e)
                time.sleep(5)

    def build_streamers(self):
        streamer_index = 0

        ## Get Twitch Streamer Data
        try:
            streamerdata = self.fetch_twitch_streams()
            print(streamerdata)

            for idx,x in enumerate(streamerdata):
                streamer_img = "/icons/streamers/"+ x + ".bmp"
                if self._debug:
                    print(streamer_img)
                try:
                    streamer_file = open(streamer_img, "rb")
                except OSError as e:
                    streamer_file = open(self._settings["default_twitch_icon"], "rb")
                img = displayio.OnDiskBitmap(streamer_file)
                img_sprite = displayio.TileGrid(img, pixel_shader=displayio.ColorConverter(), x=streamer_index*34, y=2)
                self._display_groups["stream_group"].append(img_sprite)
                streamer_index = streamer_index + 1
        except (KeyError, ValueError, RuntimeError) as e:
            self._debug_error_counter += 1
            print("Failed to get twitch streamer data\n", e)
            time.sleep(5)

    def build_display(self):
        try:
            self._led.value = True
            time.sleep(1)

            if self._debug:
                print("Building display")

            self.reset_display_groups()
            self._debug_error_counter = 0
            self._debug_refresh_counter += 1

            self.build_datetime()
            self.build_weather()
            self.build_streamers()
            self.build_sports()

            self._debug_total_error_counter += self._debug_error_counter

            ## Build Display
            updated_area = label.Label(terminalio.FONT, text=self._updated)
            updated_area.x = 275
            updated_area.y = 230
            self._display_groups["updated_group"].append(updated_area)

            if self._debug:
                memory_area = label.Label(terminalio.FONT, text="a:" + str(gc.mem_alloc()) + " f:" + str(gc.mem_free()))
                memory_area.x = 10
                memory_area.y = 230
                self._display_groups["memory_group"].append(memory_area)

                error_area = label.Label(terminalio.FONT, text="r:" +str(self._debug_refresh_counter) + " e:" + str(self._debug_error_counter) + "/" + str(self._debug_total_error_counter) + " r:" + str(self._debug_reset_counter) + "/" + str(self._debug_total_reset_counter))
                error_area.x = 115
                error_area.y = 230
                self._display_groups["error_group"].append(error_area)

            display_group = displayio.Group()
            display_group.append(self._display_groups["weather_group"])
            display_group.append(self._display_groups["days_group"])
            display_group.append(self._display_groups["temp_group"])
            display_group.append(self._display_groups["stream_group"])
            display_group.append(self._display_groups["sports_group"])
            display_group.append(self._display_groups["updated_group"])

            if self._debug:
                display_group.append(self._display_groups["memory_group"])
                display_group.append(self._display_groups["error_group"])

            board.DISPLAY.root_group = display_group

            self._led.value = False
            self._debug_reset_counter = 0

            if self._debug:
                print("Done building display")
        except (RuntimeError) as re:
            print("Error building display\n", re)
            gc.collect()
        except (TimeoutError, BrokenPipeError) as te:
            # Defensive exception handling for TimeoutError: Timed out waiting for SPI char
            # Defensive exception handling for BrokenPipeError: Expected XX but got YY
            print("TimeoutError/BrokenPipeError in building display, attempt " + str(self._debug_reset_counter) + ", retrying:\n", te)
            self._debug_reset_counter += 1
            self._debug_total_reset_counter += 1

            if self._debug_reset_counter >= 5:
                    board.DISPLAY.root_group = displayio.CIRCUITPYTHON_TERMINAL

            if self._debug_reset_counter <= 20:
                gc.collect()
                self._esp.reset()
                time.sleep(15)
                self.connect_wifi()
