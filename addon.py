from datetime import datetime, timezone, timedelta
from uuid import uuid4
import base64
import json
import os
import requests
import sys
import time
import tzlocal
import urllib.parse
import xbmc
import xbmcgui
import xbmcaddon
import xbmcplugin
import xbmcvfs


headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"}

__addon__ = xbmcaddon.Addon()
__addonname__ = __addon__.getAddonInfo('name')
data_dir = xbmcvfs.translatePath(__addon__.getAddonInfo('profile'))

base_url = sys.argv[0]
__addon_handle__ = int(sys.argv[1])
args = urllib.parse.parse_qs(sys.argv[2][1:])
lang = "de" if xbmc.getLanguage(xbmc.ISO_639_1) == "de" else "en"


def build_url(query):
    """Get the addon url based on Kodi request"""

    return f"{base_url}?{urllib.parse.urlencode(query)}"


def login(device=False):
    auth_url = "https://auth.waipu.tv/oauth/token"

    # GET TOKEN
    try:
        with open(data_dir + "token.json", "r") as f:
            token = json.loads(f.read())

        deviceid = token["uuid"]

        auth_post = {'refresh_token': token["refresh_token"], 'grant_type': 'refresh_token', 'waipu_device_id': deviceid}
    
    except:

        deviceid = str(uuid4())

        __login = __addon__.getSetting("username")
        __password = __addon__.getSetting("password")

        # LOGIN VIA EMAIL/PW (waipu.tv)
        if __login != "" and __password != "":
            auth_post = {'username': __login, 'password': __password, 'grant_type': 'password', 'waipu_device_id': deviceid}
        
        # LOGIN VIA DEVICE REGISTRATION (waipu TV / o2 TV)
        else:
        
            dialog = xbmcgui.Dialog()
            provider_list = ['waipu.tv', 'o2 TV']
            provider_config = [{"tenant": "waipu", "verification_uri": "waipu.tv/anmelden"}, {"tenant": "o2", "verification_uri": "o2.de/tv-login"}]
            
            ret = dialog.select('Bitte wählen Sie Ihren Provider aus.', provider_list)

            if ret == -1:
                return

            url = "https://auth.waipu.tv/oauth/device_authorization"
            data = {"client_id": provider_config[ret]["tenant"], "waipu_device_id": deviceid}

            headers.update({'Authorization': 'Basic YW5kcm9pZENsaWVudDpzdXBlclNlY3JldA==', 'content-type': 'application/json'})

            token_page = requests.post(url, timeout=30, headers=headers, data=json.dumps(data))

            try:
                token_result = token_page.json()
                token = token_result["device_code"]
                user_code = token_result["user_code"]
            except Exception as e:
                xbmcgui.Dialog().notification(__addonname__, "Die Geräte-Anmeldung ist fehlgeschlagen.", xbmcgui.NOTIFICATION_ERROR)
                return
            
            del headers["content-type"]

            dialog = xbmcgui.Dialog()
            dialog.ok(provider_list[ret] + ": Aktivieren Sie Ihr Gerät", f'Besuchen Sie die Webseite: [B]{provider_config[ret]["verification_uri"]}[/B]\nGeben Sie dort den folgenden Code ein: [B]{user_code}[/B]\nNach erfolgreicher Login-Bestätigung kann dieses Fenster geschlossen werden.')
            auth_post = {'device_code': token, 'grant_type': 'urn:ietf:params:oauth:grant-type:device_code', 'waipu_device_id': deviceid}
    
    auth = requests.post(auth_url, headers=headers, data=auth_post).json()

    # SAVE AND RETURN TOKEN
    try:
        auth_data = {
            "refresh_token": auth["refresh_token"],
            "access_token": auth["access_token"],
            "uuid": deviceid
        }
    except:
        if os.path.exists(data_dir + "token.json"):
            os.remove(data_dir + "token.json")
            return login()
        else:
            if __login != "" and __password != "":
                xbmcgui.Dialog().notification(__addonname__, "Die Anmeldung ist fehlgeschlagen (falsche Zugangsdaten).", xbmcgui.NOTIFICATION_ERROR)
            else:
                xbmcgui.Dialog().notification(__addonname__, "Die Anmeldung ist fehlgeschlagen.", xbmcgui.NOTIFICATION_ERROR)
            return

    try:
        if not os.path.exists(data_dir):
            os.mkdir(data_dir)
        with open(data_dir + "token.json", "w") as f:
            f.write(json.dumps(auth_data))
        if not device:
            return auth_data
    except:
        xbmcgui.Dialog().notification(__addonname__, f"Die Zugangsdaten können nicht gespeichert werden.", xbmcgui.NOTIFICATION_ERROR)
        return
    
     # DEVICE CAPABILITIES
    device_url = "https://device-capabilities.waipu.tv/api/device-capabilities"

    device_post = {"appVersion": "WEB_CLIENT@3.42.0", "manufacturer": "", "model": "", "platform": "", "type": "web"}
    device_headers = {"Authorization": f"Bearer {auth['access_token']}", "Content-Type": "application/vnd.dc.device-info-v1+json"}
    
    device_page = requests.post(device_url, headers=device_headers, data=json.dumps(device_post))
    device_resp = device_page.json()
    auth_data.update({"device_token": device_resp["token"]})
    
    return auth_data


def get_license(token):
    header, payload, sig = token.split(".")
    payload = payload.replace("_", "/").replace("-", "+")
    decoded = json.loads(base64.b64decode(payload + '=' * (-len(payload) % 4)))

    license = {'merchant': 'exaring', 'sessionId': 'default', 'userId': decoded["userHandle"]}
    return base64.b64encode(json.dumps(license).encode()).decode()


def playback(stream_url, license_str, restart=0):
    title = xbmc.getInfoLabel("ListItem.Title")
    thumb = xbmc.getInfoLabel("ListItem.Thumb")
    plot = xbmc.getInfoLabel("ListItem.Plot")
    genre = xbmc.getInfoLabel("ListItem.Genre")
    year = xbmc.getInfoLabel("ListItem.Year")
    director = xbmc.getInfoLabel("ListItem.Director")
    duration = xbmc.getInfoLabel("ListItem.Duration")

    li = xbmcgui.ListItem(path=stream_url)

    li.setProperty('inputstream', 'inputstream.adaptive')
    li.setProperty('inputstream.adaptive.manifest_type', 'mpd')
    li.setProperty("inputstream.adaptive.license_type", "com.widevine.alpha")
    li.setProperty('inputstream.adaptive.license_key', f'https://drm.wpstr.tv/license-proxy-widevine/cenc/|user-agent={xbmc.getUserAgent()}&content-type=text%2Fxml&x-dt-custom-data={license_str}|R{{SSM}}|JBlicense')
    li.setProperty("IsPlayable", "true")

    li.setInfo("video", {"title": title, 'genre': genre, 'year': year, 'director': director, 'duration': duration})
    li.setArt({'thumb': thumb})
    li.setInfo('video', {'plot': plot})

    xbmcplugin.setResolvedUrl(__addon_handle__, True, li)

    xbmc.Player().play(item=stream_url, listitem=li)
    
    if restart != 0:
        while not xbmc.Player().isPlaying():
            time.sleep(1)
        while xbmc.Player().getTime() == 0:
            time.sleep(1)
        xbmc.Player().seekTime(0.000)


def play_vod(sub, con, id):
    token = login()
    if not token:
        return
    headers.update({"Authorization": f"Bearer {token['access_token']}"})

    license_str = get_license(token["access_token"])
    
    content_url = f"https://tuner.wpstr.tv/microsites/{sub}/categories/{con}/videos/{id}"
    stream_data = requests.get(content_url, headers=headers).json()
    
    stream_url  = stream_data["player"]["mpd"]
    
    playback(stream_url, license_str)


def live(id=None, restart=0, page=0):
    get_favorites = True if __addon__.getSetting("fav") == "true" else False

    token = login(True)
    if not token:
        return
    headers.update({"Authorization": f"Bearer {token['access_token']}"})

    if id:
        headers.update({
            "Content-Type": "application/vnd.streamurlprovider.stream-url-request-v1+json",
            "X-Device-Token": token["device_token"]
        })

        license_str = get_license(token["access_token"])

        manifest_url = "https://stream-url-provider.waipu.tv/api/stream-url"
        manifest_restart = '"startTime": ' + str(restart) + '.000, "startTimeReason": "restart", ' if restart > 0 else ""
        manifest_post = '{"stream": {"station": "' + str(id) + '", ' + manifest_restart + '"protocol": "dash", "requestMuxInstrumentation": false}}'

        stream_url = requests.post(manifest_url, headers=headers, data=manifest_post).json()["streamUrl"]
        
        playback(stream_url, license_str, restart)
        return


    url = "https://user-stations.waipu.tv/api/stations?omitted=false"
    config_url = "https://web-proxy.waipu.tv/station-config"

    channels = requests.get(url, timeout=5, headers=headers).json()
    config = requests.get(config_url).json()
    new_tv = {i["id"]: i["newTv"] for i in config["stations"]}
    logos = {i["id"]: i["logoTemplateUrl"] for i in config["stations"]}

    if get_favorites:
        channels = [i for i in channels if i["userSettings"]["favorite"]]

    for number, item in enumerate(channels):
        if number < page*10:
            continue
        if number > 9+page*10:
            li = xbmcgui.ListItem(label="Weitere Kanäle...")
            url = build_url({"mode": "live", "page": str(page+1)})
            xbmcplugin.addDirectoryItem(handle=__addon_handle__, url=url, listitem=li, isFolder=True)
            break

        if not item["locked"]:
            if item["userSettings"]["visible"]:
                
                de = None
                try:
                    nxt = ""
                    nxt_id = None
                    nxt_count = 0
                    
                    dt1 = datetime.now() - timedelta(hours=4)
                    h1 = f"{(dt1.hour // 4) * 4:02d}"
                    details_1 = requests.get(f'https://epg-cache.waipu.tv/api/grid/{item["stationId"]}/{str(dt1.year)}-{("0" if len(str(dt1.month)) == 1 else "") + str(dt1.month)}-{("0" if len(str(dt1.day)) == 1 else "") + str(dt1.day)}T{h1}:00:00.000Z').json()
                    
                    dt2 = datetime.now()
                    h2 = f"{(dt2.hour // 4) * 4:02d}"
                    details_2 = requests.get(f'https://epg-cache.waipu.tv/api/grid/{item["stationId"]}/{str(dt2.year)}-{("0" if len(str(dt2.month)) == 1 else "") + str(dt2.month)}-{("0" if len(str(dt2.day)) == 1 else "") + str(dt2.day)}T{h2}:00:00.000Z').json()

                    dt = details_1 + details_2
                    details = {}
                    for d in dt:
                        if not details.get(d["id"]):
                            details[d["id"]] = d
                    details = [details[d] for d in details.keys()]
                    
                    for d in details:
                        tb = datetime(*(time.strptime(d["startTime"], "%Y-%m-%dT%H:%M:%SZ")[0:6])).replace(tzinfo=timezone.utc)
                        te = datetime(*(time.strptime(d["stopTime"], "%Y-%m-%dT%H:%M:%SZ")[0:6])).replace(tzinfo=timezone.utc)
                        if tb <= datetime.now(timezone.utc) < te:
                            try:
                                more_details = requests.get(f'https://epg-cache.waipu.tv/api/programs/{d["id"]}').json()
                                d["md"] = more_details
                            except:
                                d["md"] = {"textContent": {"descLong": ""}}
                            d["bcd"] = f'{tb.astimezone(tzlocal.get_localzone()).strftime("%H:%M")} - {te.astimezone(tzlocal.get_localzone()).strftime("%H:%M")}'
                            de = d
                        elif datetime.now(timezone.utc) < tb:
                            if nxt_count < 1:
                                nxt = nxt + f'[B]{tb.astimezone(tzlocal.get_localzone()).strftime("%H:%M")} - {te.astimezone(tzlocal.get_localzone()).strftime("%H:%M")}[/B]: {d["title"]}\n'
                                nxt_id = d["id"] if not d["recordingForbidden"] else None
                            nxt_count = nxt_count + 1
                    de["nxt"] = nxt if nxt else None
                except:
                    pass
                
                ch_logo = logos[item["stationId"]].replace(
                    "${streamQuality}", item["streamQuality"]).replace(
                        "${shape}", "standard").replace("${resolution}", "320x180")
                
                if de:
                    li = xbmcgui.ListItem(label=f'[B]{item["displayName"]}[/B] | {de["title"]}{(" | "+de["episodeTitle"]) if de.get("episodeTitle") else ""}')
                    li.setInfo('video', {'title': f'[B]{item["displayName"]}[/B] | {de["title"]}{(" | "+de["episodeTitle"]) if de.get("episodeTitle") else ""}', "plot": f'[COLOR=yellow][B]{de["bcd"]}: [/B]{de["title"]}[/COLOR]\n{de["nxt"] if de.get("nxt") else ""}\n{de["md"]["textContent"].get("descLong", "")}'})
                    li.setArt({"thumb": ch_logo, "poster": de.get("previewImage", "").replace("${resolution}", "1920x1080"), "fanart": de.get("previewImage", "").replace("${resolution}", "1920x1080")})
                    restart = int(datetime(*(time.strptime(de["startTime"], "%Y-%m-%dT%H:%M:%SZ")[0:6])).replace(tzinfo=timezone.utc).timestamp())
                    context_list = []
                    desc_restart_url = build_url({'mode': 'live', 'restart': restart, 'id': item["stationId"]})
                    context_list.append(("Von Beginn ansehen", f"RunPlugin({desc_restart_url})"))
                    if not d["recordingForbidden"]:
                        desc_now_url = build_url({'mode': 'add_rec', 'id': de["id"]})
                        context_list.append(("Aktuelle Sendung aufnehmen", f"RunPlugin({desc_now_url})"))
                    if nxt_id:
                        desc_next_url = build_url({'mode': 'add_rec', 'id': nxt_id})
                        context_list.append(("Nächste Sendung aufnehmen", f"RunPlugin({desc_next_url})"))
                    li.addContextMenuItems(context_list)
                else:
                    li = xbmcgui.ListItem(label=item["displayName"])
                    li.setInfo('video', {'title': item["displayName"], "plot": de["title"] if de else ""})
                    li.setArt({"thumb": ch_logo, "icon": ch_logo})
                    restart = 0
                url = build_url({"mode": "live", "restart": 0, "id": item["stationId"]})
                xbmcplugin.addDirectoryItem(handle=__addon_handle__, url=url, listitem=li, isFolder=False)

    xbmcplugin.endOfDirectory(__addon_handle__)


def rec(id=None, page=0, series=None):
    token = login()
    if not token:
        return
    headers.update({"Authorization": f"Bearer {token['access_token']}"})

    if id:
        headers.update({"Accept": "application/vnd.waipu.recording-streaming-detail-v4+json"})
        rec_start_url = f"https://recording.waipu.tv/api/recordings/{id}/streamingdetails"

        license_str = get_license(token["access_token"])

        try:
            stream_url    = [i for i in requests.get(rec_start_url, headers=headers).json()["streams"] if i["protocol"] == "MPEG_DASH"][0]["href"]
        except:
            xbmcgui.Dialog().notification(__addonname__, "Die Aufnahme kann aktuell nicht wiedergegeben werden.", xbmcgui.NOTIFICATION_ERROR)
            return
        
        playback(stream_url, license_str)
        return
    
    headers.update({"Accept": "application/vnd.waipu.recordings-v4+json"})

    menu_listing = []

    if series:
        rec_url = f"https://recording.waipu.tv/api/recordings?recordingGroup={series}"
    else:
        rec_url = "https://recording.waipu.tv/api/recordings"

    rec_list = requests.get(rec_url, headers=headers).json()

    headers.update({"Accept": "application/vnd.waipu.recording-v4+json"})

    number = 0
    for item in reversed(rec_list):
        if number < page*20:
            continue
        if number > 19+page*20:
            li = xbmcgui.ListItem(label="Weitere Aufnahmen...")
            url = build_url({"mode": "rec", "page": str(page+1)})
            xbmcplugin.addDirectoryItem(handle=__addon_handle__, url=url, listitem=li, isFolder=True)
            break

        try:
            details = requests.get(f"https://recording.waipu.tv/api/recordings/{item['id']}", headers=headers).json()
        except Exception as e:
            details = str(e)
        if item["status"] == "SCHEDULED" and ((not details.get("recordingGroup")) or series):
            if __addon__.getSetting("scheduled") == "true":
                continue
            item["title"] = "[COLOR=yellowgreen][B](Geplant) [/B][/COLOR] " + item["title"]
        if item["status"] == "RECORDING" and ((not details.get("recordingGroup")) or series):
            item["title"] = "[COLOR=yellow][B](Laufend) [/B][/COLOR] " + item["title"]
        if details.get("recordingGroup") and not series:
            item["title"] = "[COLOR=yellow][B](Serie)[/B][/COLOR] " + f'[B]{item["stationDisplay"]}[/B] | ' + item["title"]
            li = xbmcgui.ListItem(label=item["title"])
            url = build_url({"mode": "rec", "series": details["recordingGroup"]})
            menu_listing.append((url, li, True))
        else:
            li = xbmcgui.ListItem(label=f'[B]{item["stationDisplay"]}[/B] | {item["title"]}{" | "+item["episodeTitle"] if item.get("episodeTitle") else ""} ({datetime(*(time.strptime(details["startTime"], "%Y-%m-%dT%H:%M:%S%z")[0:6])).strftime("%d.%m.%Y %H:%M")})')
            li.setInfo('video', {'title': item["title"], 'plot': details['programDetails']['textContent']['descLong'] if details else ''})
            desc_now_url = build_url({'mode': 'del_rec', 'id': item["id"]})
            li.addContextMenuItems([("Aufnahme löschen", f"RunPlugin({desc_now_url})")])
            url = build_url({"mode": "rec", "id": item["id"]})
            menu_listing.append((url, li, False))
        if item.get("previewImage"):
            li.setArt({"thumb": item["previewImage"].replace("${resolution}", "1920x1080"), "fanart": item["previewImage"].replace("${resolution}", "1920x1080")})
        number = number + 1

    xbmcplugin.addDirectoryItems(__addon_handle__, menu_listing, len(menu_listing))
    xbmcplugin.endOfDirectory(__addon_handle__)


def vod(sub=None, con=None):
    token = login()
    if not token:
        return
    headers.update({"Authorization": f"Bearer {token['access_token']}"})
    
    if sub:
        modules = requests.get(f"https://tuner.wpstr.tv/microsites/{sub}/contents", headers=headers).json()["categories"]
        if con:
            main    = [c for i in modules for c in i["contents"] if i["id"] == con]
        else:
            main    = [i for i in modules]
    else:
        modules = requests.get("https://waiputhek.waipu.tv/api/pages/highlights", headers=headers).json()["modules"]
        main    = [c for i in modules for c in i["contents"] if i["id"] == "top-mediatheken"]

    menu_listing = []

    for item in main:
        img = item.get("img", item["video"].get("img") if con else item["contents"][0]["video"].get("img")) if sub else item["links"][0]["href"]

        li = xbmcgui.ListItem(label=item.get("title", item["video"]["title"] if con else ""))
        li.setArt({"thumb": img, "fanart": img if sub else None})
        li.setInfo('video', {
            'title': item.get("title", item["video"]["title"] if con else ""), 
            'genre': item.get("genre"),
            'plot': item["video"]["description"] if con else item["description"] if item["description"] != "" else item["title"]
        })
        
        if con:
            url_dict = {"mode": "play_vod", "sub": sub, "con": con, "id": item["video"]["programID"].split(":")[-1]}
        else:
            url_dict = {"mode": "vod", "sub": sub if sub else item["channel"]}
        
            if sub:
                url_dict.update({"con": item["id"]})
            
        url = build_url(url_dict)
        menu_listing.append((url, li, False if con else True))

    xbmcplugin.addDirectoryItems(__addon_handle__, menu_listing, len(menu_listing))
    xbmcplugin.endOfDirectory(__addon_handle__)


def add_rec(rec_id):
    token = login()
    if not token:
        return
    headers.update({"Authorization": f"Bearer {token['access_token']}", "Content-Type": "application/vnd.waipu.recording-create-v4+json"})

    url = "https://recording.waipu.tv/api/recordings"
    post_data = '{"programId": "' + rec_id + '"}'

    try:
        add_rec_req = requests.post(url, headers=headers, data=post_data).json()
        rec_id = add_rec_req["recordingId"]
        xbmcgui.Dialog().notification(__addonname__, "Die Sendung wurde zu den Aufnahmen hinzugefügt.", xbmcgui.NOTIFICATION_INFO)
    except Exception as e:
        xbmcgui.Dialog().notification(__addonname__, "Die Sendung konnte nicht zu den Aufnahmen hinzugefügt werden.", xbmcgui.NOTIFICATION_ERROR)

def del_rec(rec_id):
    token = login()
    if not token:
        return
    headers.update({"Authorization": f"Bearer {token['access_token']}", "Content-Type": "application/vnd.waipu.recording-ids-v4+json"})

    url = "https://recording.waipu.tv/api/recordings"
    post_data = '{"ids": ["' + rec_id + '"], "groupIds": [], "recordingSelection": ["AVAILABLE"]}'

    add_rec_req = requests.delete(url, headers=headers, data=post_data)
    
    if add_rec_req.status_code == 204:
        xbmcgui.Dialog().notification(__addonname__, "Die Aufnahme wurde gelöscht.", xbmcgui.NOTIFICATION_INFO)
        xbmc.executebuiltin('Container.Refresh')
    else:
        xbmcgui.Dialog().notification(__addonname__, "Die Aufnahme konnte nicht gelöscht werden.", xbmcgui.NOTIFICATION_ERROR)


def router(item):
    """Router function calling other functions of this script"""

    params = dict(urllib.parse.parse_qsl(item[1:]))

    if params:
        if params.get("mode") == "live":
            live(params.get("id"), int(params.get("restart", 0)), int(params.get("page", 0)))
        if params.get("mode") == "rec":
            rec(params.get("id"), int(params.get("page", 0)), params.get("series"))
        elif params.get("mode") == "vod":
            vod(params.get("sub"), params.get("con"))
        elif params.get("mode") == "play_vod":
            play_vod(params.get("sub"), params.get("con"), params.get("id"))
        elif params.get("mode") == "add_rec":
            add_rec(params.get("id"))
        elif params.get("mode") == "del_rec":
            del_rec(params.get("id"))
    else:  
        # MAIN
        main_listing = []
        for mode in [("live", "Live TV"), ("rec", "Aufnahmen"), ("vod", "waiputhek")]:
            url = build_url({'mode': mode[0]})
            li = xbmcgui.ListItem(mode[1])
            main_listing.append((url, li, True))

        xbmcplugin.addDirectoryItems(__addon_handle__, main_listing, len(main_listing))
        xbmcplugin.endOfDirectory(__addon_handle__)

if __name__ == "__main__":
    router(sys.argv[2])
