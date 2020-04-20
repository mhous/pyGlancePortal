import time
import gc
import board
import displayio
import digitalio
import terminalio
import busio
import neopixel
from adafruit_esp32spi import adafruit_esp32spi, adafruit_esp32spi_wifimanager
from adafruit_display_text import label

try:
    from secrets import secrets
except ImportError:
    print("Wifi and API secrets are kept in secrets.py, please add them there!")
    raise

class PyGlancePortal:
    def __init__(self, debug=False):
        self._settings = {
            "wifi_ssid": secrets["ssid"],
            "wifi_password": secrets["password"],
            "aio_username": secrets["aio_username"],
            "aio_key": secrets["aio_key"],
            "forecast_url": secrets["darksky_api_forecast"],
            "twitch_url": secrets["twitch_api_streams"],
            "twitch_key": secrets["twitch_api_key"],
            "twitch_streamers": secrets["twitch_api_streamers"],
            "mixer_url": secrets["mixer_api_streams"],
            "mixer_key": secrets["mixer_api_key"],
            "mixer_streamers": secrets["mixer_api_streamers"],
            "nhl_url": secrets["sports_api_nhl"],
            "nhl_teams": secrets["sports_api_nhl_teams"],
            "nfl_url": secrets["sports_api_nfl"],
            "nfl_teams": secrets["sports_api_nfl_teams"],
            "mlb_url": secrets["sports_api_mlb"],
            "mlb_teams": secrets["sports_api_mlb_teams"],
            "prem_url": secrets["sports_api_prem"],
            "prem_teams": secrets["sports_api_prem_teams"],
            "default_weather_icon": "/icons/weather/unknown.bmp",
            "default_twitch_icon": "/icons/streamers/twitch.bmp",
            "default_mixer_icon": "/icons/streamers/mixer.bmp"
        }

        self._debug = debug
        self._debug_refresh_counter = 0
        self._debug_error_counter = 0
        self._debug_total_error_counter = 0
        self._today = 0
        self._updated = ""
        self._display_groups = {}
        self.reset_display_groups()
        

        # PyPortal ESP32 Setup
        esp32_cs = digitalio.DigitalInOut(board.ESP_CS)
        esp32_ready = digitalio.DigitalInOut(board.ESP_BUSY)
        esp32_reset = digitalio.DigitalInOut(board.ESP_RESET)
        spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
        esp = adafruit_esp32spi.ESP_SPIcontrol(spi, esp32_cs, esp32_ready, esp32_reset)
        status_light = neopixel.NeoPixel(board.NEOPIXEL, 1, brightness=0.2)
        self._led = digitalio.DigitalInOut(board.D13)
        self._led.direction = digitalio.Direction.OUTPUT

        # WiFi Setup
        if self._debug:
            print("Visible SSIDs:")
            for ap in esp.scan_networks():
                print("%s  RSSI: %d" % (str(ap["ssid"], "utf-8"), ap["rssi"]))
        
        print("Connecting configured WiFi...")
        while not esp.is_connected:
            try:
                esp.connect(secrets)
            except RuntimeError as e:
                print("Could not connect to WiFi, retrying: ",e)
                continue

        print("Connected to:", str(esp.ssid, "utf-8"), "  RSSI:", esp.rssi)
        print("IP address:", esp.pretty_ip(esp.ip_address))

        self._wifi_client = adafruit_esp32spi_wifimanager.ESPSPI_WiFiManager(esp, secrets, status_light)

        # PyPortal Board Setup
        board.DISPLAY.auto_brightness = False
        board.DISPLAY.brightness = 1

    def get_dayname(self, wday_num):
        days = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"]
        return(days[wday_num%7])

    def fetch_datetime(self):
        r = self._wifi_client.get("https://io.adafruit.com/api/v2/" + self._settings["aio_username"] + "/integrations/time/struct.json", headers={"X-AIO-KEY":self._settings["aio_key"]})
        t = r.json()
        return time.struct_time((t["year"], t["mon"], t["mday"], t["hour"], t["min"], t["sec"], t["wday"], t["yday"], t["isdst"]))

    def fetch_forecast(self):
        r = self._wifi_client.get(self._settings["forecast_url"])
        return self.parse_forecast(r.json())

    def fetch_twitch_streams(self):
        streamers = self._settings["twitch_streamers"].split(",")
        qsparam = "user_login="
        for idx,x in enumerate(streamers):
            streamers[idx] = qsparam + streamers[idx]
        r = self._wifi_client.get(self._settings["twitch_url"] + "&".join(streamers), headers={"Client-ID":self._settings["twitch_key"]})
        return self.parse_twitch_streams(r.json())
    
    def fetch_mixer_streams(self):
        streamers = list()
        for idx,x in enumerate(self._settings["mixer_streamers"].split(",")):
            s = self._settings["mixer_url"] + x
            r = self._wifi_client.get(s, headers={"Client-ID":self._settings["mixer_key"]})
            if(self.parse_mixer_streams(r.json())):
                streamers.append(x)
        return streamers

    def fetch_league(self, league, teams, league_url, group, numlive):
        if len(teams) == 0:
            print("No teams for " + league + ". Skipping.")
            return numlive
        for idx,x in enumerate(teams.split(",")):
            if self._debug:
                print(idx, " ", x, " ", league)
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
                print("No game for " + x + " " + league)
        return numlive

    def fetch_team(self, api_url, league, team):
        r = self._wifi_client.get(api_url+team)
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

    def parse_mixer_streams(self, streams_json):
        return streams_json["online"] == True

    def parse_team(self, league, team, team_json):
        t = ""
        if team_json["sports"][0]["leagues"][0]["events"][0]["status"] == "in":
            t = league + "/" + team
            if self._debug:
                print(team_json["sports"][0]["leagues"][0]["events"][0]["shortName"])
                print(team_json["sports"][0]["leagues"][0]["events"][0]["status"])
        return t
    
    def reset_display_groups(self):
        self._display_groups = {
            "weather_group": displayio.Group(max_size=6),
            "days_group": displayio.Group(max_size=6),
            "temp_group": displayio.Group(max_size=6),
            "stream_group": displayio.Group(max_size=6),
            "sports_group": displayio.Group(max_size=6),
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
            print("Failed to get time data, retrying\n", e)
            self._wifi_client.reset()
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
        except (ValueError, RuntimeError) as e:
            self._debug_error_counter += 1
            print("Failed to get forecast data, retrying\n", e)
            self._wifi_client.reset()
            time.sleep(5)
    
    def build_sports(self):
        live_teams = 0

        try:
            current_league = "nhl"
            live_teams = self.fetch_league(current_league, self._settings["nhl_teams"], self._settings["nhl_url"], self._display_groups["sports_group"], live_teams)
        except (KeyError, ValueError, RuntimeError) as e:
            self._debug_error_counter += 1
            print("Failed to get " + current_league + " data\n", e)
            self._wifi_client.reset()
            time.sleep(5)

        try:
            current_league = "nfl"
            live_teams = self.fetch_league(current_league, self._settings["nfl_teams"], self._settings["nfl_url"], self._display_groups["sports_group"], live_teams)
        except (KeyError, ValueError, RuntimeError) as e:
            self._debug_error_counter += 1
            print("Failed to get " + current_league + " data\n", e)
            self._wifi_client.reset()
            time.sleep(5)

        try:
            current_league = "mlb"
            live_teams = self.fetch_league(current_league, self._settings["mlb_teams"], self._settings["mlb_url"], self._display_groups["sports_group"], live_teams)
        except (KeyError, ValueError, RuntimeError) as e:
            self._debug_error_counter += 1
            print("Failed to get " + current_league + " data\n", e)
            self._wifi_client.reset()
            time.sleep(5)

        # try:
        #     current_league = "prem"
        #     live_teams = self.fetch_league(current_league, self._settings["prem_teams"], self._settings["prem_url"], self._display_groups["sports_group"], live_teams)
        # except (KeyError, ValueError, RuntimeError) as e:
        #     self._debug_error_counter += 1
        #     print("Failed to get " + current_league + " data\n", str(e))
        #     self._wifi_client.reset()
        #     time.sleep(5)

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
        except (ValueError, RuntimeError) as e:
            self._debug_error_counter += 1
            print("Failed to get twitch streamer data\n", e)
            self._wifi_client.reset()
            time.sleep(5)

        ## Get Mixer Streamer Data
        try:
            streamerdata = self.fetch_mixer_streams()
            print(streamerdata)

            for idx,x in enumerate(streamerdata):
                streamer_img = "/icons/streamers/"+ x + ".bmp"
                if self._debug:
                    print(streamer_img)
                try:
                    streamer_file = open(streamer_img, "rb")
                except OSError as e:
                    streamer_file = open(self._settings["default_mixer_icon"], "rb")
                img = displayio.OnDiskBitmap(streamer_file)
                img_sprite = displayio.TileGrid(img, pixel_shader=displayio.ColorConverter(), x=streamer_index*34, y=2)
                self._display_groups["stream_group"].append(img_sprite)
                streamer_index = streamer_index + 1
        except (ValueError, RuntimeError) as e:
            self._debug_error_counter += 1
            print("Failed to get mixer streamer data\n", e)
            self._wifi_client.reset()
            time.sleep(5)
    
    def build_display(self):
        self._led.value = True
        time.sleep(1.0)

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
        updated_area.x = 265
        updated_area.y = 230
        self._display_groups["updated_group"].append(updated_area)

        if self._debug:
            memory_area = label.Label(terminalio.FONT, text="a:" + str(gc.mem_alloc()) + " f:" + str(gc.mem_free()))
            memory_area.x = 10
            memory_area.y = 230
            self._display_groups["memory_group"].append(memory_area)

            error_area = label.Label(terminalio.FONT, text="r:"+str(self._debug_refresh_counter) + " e:" + str(self._debug_error_counter) + " te:" + str(self._debug_total_error_counter))
            error_area.x = 125
            error_area.y = 230
            self._display_groups["error_group"].append(error_area)

        display_group = displayio.Group(max_size=36)
        display_group.append(self._display_groups["weather_group"])
        display_group.append(self._display_groups["days_group"])
        display_group.append(self._display_groups["temp_group"])
        display_group.append(self._display_groups["stream_group"])
        display_group.append(self._display_groups["sports_group"])
        display_group.append(self._display_groups["updated_group"])

        if self._debug:
            display_group.append(self._display_groups["memory_group"])
            display_group.append(self._display_groups["error_group"])

        board.DISPLAY.show(display_group)

        self._led.value = False

        if self._debug:
            print("Done building display")