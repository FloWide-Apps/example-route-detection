import streamlit as st
import pandas as pd
from streamlit_flowide import PlayBack
import json

import datetime

import os

from flowide.env import env
from flowide.connectors.database import Databases
from flowide.tools import make_motion_model
from flowide.tools.routes import RouteDefiner,Routes


class TrajectoryJump(RouteDefiner):

    def __init__(self,threshold):
        self._threshold = threshold
        self._in_route = False

    def init(self,df,motion_models_by_time,motion_models):
        diffsBetweenTrajs = motion_models_by_time['startTime'].shift(periods=-1, fill_value=motion_models_by_time['endTime'][-1]) - motion_models_by_time['endTime']
        self._jumps = diffsBetweenTrajs > self._threshold
        self._in_route = False


    def is_route_start(self,row,index) -> bool:
        if not self._in_route:
            self._in_route = True
            return True
        else:
            return False

    def is_route_end(self,row,index) -> bool:
        jump =  bool(self._jumps.get(index))
        self._in_route = not jump
        return jump


def stats_to_file(routes: Routes,date: pd.Timestamp,carrier_name: str):
    stat_data = {
        "numberOfRoutes":len(routes),
        "numberOfStops":int(routes.number_of_stops),
        "sumOfStopTime":float(routes.sum_stop_time),
        "sumOfMovingTime":float(routes.sum_moving_time),
        "sumOfDistance":float(routes.sum_distance)
    }

    date_string = date.date().strftime("%d/%m/%Y")
    if os.path.exists("stats.json"):
      with open("stats.json","r+") as f:
        file_data = json.loads(f.read())

        if not file_data.get(date_string):
          file_data[date_string] = {}

        file_data[date_string][carrier_name] = stat_data
        f.seek(0)
        f.write(json.dumps(file_data))
        f.truncate()
    else:
      file_data = {}
      file_data[date_string] = {}
      file_data[date_string][carrier_name] = stat_data
      with open("stats.json","w") as f:
        f.write(json.dumps(file_data))





for carrier in env.carriers:
    carrier['checked'] = st.sidebar.checkbox(f'{carrier["name"]} ({carrier["color"]}) ')

date = pd.Timestamp(st.sidebar.date_input('Date'))
time_hh = st.sidebar.number_input("Hour",0,23,1)
time_mm = st.sidebar.number_input("Minutes",0,59,1)
duration_s = st.sidebar.number_input("Duration [min]",0,120,1) * 60

from_date = pd.Timestamp.combine(date,datetime.time(time_hh,time_mm,0))
to_date = from_date + pd.Timedelta(duration_s,unit="sec") 

stable_ransac = {'max_trials': 100, 'min_samples': 0.4, 'residual_threshold': 1.0 * 1.0}
spline_ransac = {'max_trials': 1000, 'min_samples': 0.8, 'residual_threshold': 1. * 1.}


db = Databases()
with db.history_connection() as history:

    for carrier in env.carriers:
        if not carrier['checked']:
            continue
        with st.expander(carrier["name"]):
            data = history.get_history(
                from_date,
                to_date,
                (history.Locations.position_x,'posx'),
                (history.Locations.position_y,'posy'),
                where_clause={
                    history.Tables.LOCATIONS : history.Locations.primaryid == carrier["tag"]
                }
            )
            if data.empty:
                st.warning(f'No data for {carrier["name"]} between {from_date} and {to_date}')
                continue
            data.index = data.index.tz_convert(None)
            
            routes = Routes(data,env.zones.curve_fitting,TrajectoryJump('30s'))
            st.write("Number of routes: ",len(routes))
            st.write("Number of stops: ",routes.number_of_stops)
            st.write("Sum of stop time: ",routes.sum_stop_time)
            st.write("Sum of moving time: ",routes.sum_moving_time)
            st.write("Sum of distance: ", routes.sum_distance)

            stats_to_file(routes,date,carrier["name"])
            selected_route = st.selectbox('Select a route',list(range(0,len(routes))))
            PlayBack(env.common.map_config,list(routes.generate_playback_data(None,icon=carrier["icon"],color=carrier["color"])))
