import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

import requests
import pandas as pd
from pandas.io.json import json_normalize

from constants import events

OFFLINE = True if os.environ.get('OFFLINE', 'false') == 'true' else False
SALT = os.environ['SALT'].encode()[:16]


def fetch_race(event_id, event_name, race_id, race_name):
    print(f'\tfetching race: {race_name}')
    count = 50
    offset = 0
    url = (
        f'https://eventresults-api.sporthive.com/api'
        f'/events/{event_id}'
        f'/races/{race_id}'
        '/classifications/search'
    )
    df = pd.DataFrame()
    first_run = True
    while True:
        print(f'\t\trequesting offset {offset}', end='\r')
        if OFFLINE:
            with Path(Path('.').parent, 'cached_responses', f'race_{race_id}_{offset}.json').open('r') as f:
                data = json.load(f)
        else:
            response = requests.get(
                url=url,
                params=dict(count=count, offset=offset)
            )
            data = response.json()
            with Path(Path('.').parent, 'cached_responses', f'race_{race_id}_{offset}.json').open('w') as f:
                json.dump(data, f, indent=2)

        if first_run:
            try:
                distance = data['eventRace']['race']['distanceInMeter']
                race = data['eventRace']['race']['name'].lower().replace(' ', '_')
                date = data['eventRace']['race']['date'][:10]
            except KeyError:
                print(f'\t\t{event_name} has no eventRace key. Skipping...')
                return df

            first_run = False

        for athlete in data['fullClassifications']:
            athlete_name = athlete['classification']['name']
            name_hash_object = hashlib.blake2b(athlete_name.encode(), digest_size=16, salt=SALT)
            hashed_name = name_hash_object.hexdigest()
            athlete_dict = dict(
                id=uuid4().hex,
                hashed_name=hashed_name,
                event_name=event_name,
                date=date,
                race=race,
                distance=distance,
                category=athlete['classification'].get('category', None),
                gun_time_seconds=athlete['classification'].get('gunTimeInSec', None),
                chip_time_seconds=athlete['classification'].get('chipTimeInSec', None)
            )
            for split in athlete['classification'].get('splits', []):
                cumulative_time = split.get('cumulativeTime', None)
                if cumulative_time in [None, '']:
                    continue
                hours, minutes, seconds = [int(i) for i in cumulative_time.split(':')]
                athlete_dict[f'split_{split["name"].lower()}'] = hours*3600 + minutes*60 + seconds

            athlete_df = pd.DataFrame({key: [value] for key, value in athlete_dict.items()})
            df = pd.concat([df, athlete_df], sort=False)

        if len(data['fullClassifications']) < 50:
            break

        offset += count

    print(f'\t\tfetched {offset + len(data["fullClassifications"])} results')

    with Path(Path('.').parent, 'data_single_race', f'{event_id}_{race_id}.csv').open('w') as f:
        df.to_csv(f, index=False)

    return df


def fetch_event(event_id, event_name):
    if OFFLINE:
        with Path(Path('.').parent, 'cached_responses', f'event_{event_id}.json').open('r') as f:
            data = json.load(f)
    else:
        url = (
            f'https://eventresults-api.sporthive.com/api'
            f'/events/{event_id}/races'
        )
        response = requests.get(url)
        data = response.json()

        with Path(Path('.').parent, 'cached_responses', f'event_{event_id}.json').open('w') as f:
            json.dump(data, f, indent=2)

    df = pd.DataFrame()
    for race in data['races']:
        race_df = fetch_race(event_id, event_name, race['id'], race['name'])
        df = pd.concat([df, race_df], sort=False)
    
    return df


def fetch_events():
    df = pd.DataFrame()
    for event in events:
        print(f'fetching event: {event["name"]} {event["year"]}')
        event_df = fetch_event(event['id'], event['name'])
        df = pd.concat([df, event_df], sort=False)

    with Path(Path('.').parent, 'data', 'race_results', 'results.csv').open('w') as f:
        df.to_csv(f, index=False)


if __name__ == "__main__":
    fetch_events()
