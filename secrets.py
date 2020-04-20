# This file is where you keep secret settings, passwords, and tokens!
# If you put them in the code you risk committing that info or sharing it
# which would be not great. So, instead, keep it all in this one file and
# keep it a secret.

secrets = {
    "ssid" : "", # Keep the two "" quotes around the name
    "password" : "", # Keep the two "" quotes around password
    "timezone" : "America/Chicago",  # http://worldtimeapi.org/timezones
    "aio_username" : "", # Adafruit IO username
    "aio_key" : "", # Adafruit IO key
    "darksky_api_key" : "", # Dark Sky API key
    "darksky_api_forecast" : "https://api.darksky.net/forecast/<darksky_api_key>/37.8267,-122.4233?exclude=minutely,hourly,alerts,flags", # Update API call with key and location
    "twitch_api_key" : "", # Twitch API key
    "twitch_api_streams" : "https://api.twitch.tv/helix/streams?",
    "twitch_api_streamers" : "", # Comma-delimited list of Twitch streamer handles
    "mixer_api_key" : "", # Mixer API key
    "mixer_api_streams" : "https://mixer.com/api/v1/channels/",
    "mixer_api_streamers" : "", # Comma-delimited list of Mixer streamer handles
    "sports_api_mlb" : "https://site.web.api.espn.com/apis/v2/scoreboard/header?sport=baseball&league=mlb&region=us&lang=en&contentorigin=espn&tz=America/New_York&team=",
    "sports_api_mlb_teams" : "", # Comma-delimited list of team abbreviations
    "sports_api_nfl" : "https://site.web.api.espn.com/apis/v2/scoreboard/header?sport=football&league=nfl&region=us&lang=en&contentorigin=espn&tz=America/New_York&team=",
    "sports_api_nfl_teams" : "", # Comma-delimited list of team abbreviations
    "sports_api_nhl" : "https://site.web.api.espn.com/apis/v2/scoreboard/header?sport=hockey&league=nhl&region=us&lang=en&contentorigin=espn&tz=America/New_York&team=",
    "sports_api_nhl_teams" : "", # Comma-delimited list of team abbreviations
    "sports_api_prem" : "https://site.web.api.espn.com/apis/v2/scoreboard/header?sport=soccer&league=eng.1&region=us&lang=en&contentorigin=espn&tz=America/New_York&team=",
    "sports_api_prem_teams" : "" # Comma-delimited list of team abbreviations
    }