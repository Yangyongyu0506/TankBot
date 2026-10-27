"""Acceptance-only EKF/prediction examples; no engine objects or secret enemy controller inputs."""
import math
import numpy as np

POLAR = '''import numpy as np
from tankbot import PolarTargetEstimate
PARAMS=__PARAMS__
class PolarTracker:
    def __init__(self,measurement_covariance):
        self.R=measurement_covariance;self.x=None;self.P=np.eye(4)*PARAMS['initial_variance']
    def update(self,measurements,own_pose,dt):
        z=np.array([measurements[0].range_m,measurements[0].bearing_rad],dtype=np.float64) if measurements else None
        if self.x is None:
            if z is None:return None
            angle=own_pose[2]+z[1]
            self.x=np.array([own_pose[0]+z[0]*np.cos(angle),own_pose[1]+z[0]*np.sin(angle),0.,0.])
        else:
            F=np.eye(4);F[0,2]=dt;F[1,3]=dt
            G=np.array([[dt*dt/2,0],[0,dt*dt/2],[dt,0],[0,dt]])
            self.x=F@self.x;self.P=F@self.P@F.T+G@G.T*PARAMS['process_acceleration_std']**2
            if z is not None:
                dx,dy=self.x[:2]-own_pose[:2];q=max(float(dx*dx+dy*dy),PARAMS['minimum_distance_squared']);r=np.sqrt(q)
                h=np.array([r,np.arctan2(dy,dx)-own_pose[2]])
                H=np.array([[dx/r,dy/r,0,0],[-dy/q,dx/q,0,0]])
                residual=z-h;residual[1]=np.arctan2(np.sin(residual[1]),np.cos(residual[1]))
                K=np.linalg.solve((H@self.P@H.T+self.R).T,(self.P@H.T).T).T
                self.x+=K@residual;A=np.eye(4)-K@H;self.P=A@self.P@A.T+K@self.R@K.T
        delta=self.x[:2]-own_pose[:2];bearing=np.arctan2(delta[1],delta[0])-own_pose[2]
        return PolarTargetEstimate(float(np.linalg.norm(delta)),float(np.arctan2(np.sin(bearing),np.cos(bearing))))
'''

FUSION = '''import numpy as np
from tankbot import TargetPoseEstimate
PARAMS=__PARAMS__
class FusionTracker:
    def __init__(self,gps_mount,radar_covariance,gps_covariance):
        self.a=gps_mount[0];self.Rr=radar_covariance;self.Rg=gps_covariance;self.x=None;self.P=np.eye(6)*PARAMS['initial_variance']
    def correct(self,z,h,H,R,angular=False):
        residual=z-h
        if angular:residual[1]=np.arctan2(np.sin(residual[1]),np.cos(residual[1]))
        K=np.linalg.solve((H@self.P@H.T+R).T,(self.P@H.T).T).T
        self.x+=K@residual;A=np.eye(6)-K@H;self.P=A@self.P@A.T+K@R@K.T
        self.x[4]=np.arctan2(np.sin(self.x[4]),np.cos(self.x[4]))
    def update(self,measurements_rt,gps_xy,own_pose,dt):
        zr=measurements_rt[0] if len(measurements_rt) else None
        zg=gps_xy[0] if len(gps_xy) else None
        if self.x is None:
            if zr is None or zg is None:return None
            angle=own_pose[2]+zr[1];center=own_pose[:2]+zr[0]*np.array([np.cos(angle),np.sin(angle)])
            delta=zg-center;self.x=np.array([center[0],center[1],0.,0.,np.arctan2(delta[1],delta[0]),0.])
        else:
            F=np.eye(6);F[0,2]=dt;F[1,3]=dt;F[4,5]=dt
            G=np.zeros((6,3));G[0,0]=G[1,1]=G[4,2]=dt*dt/2;G[2,0]=G[3,1]=G[5,2]=dt
            Q=np.diag([PARAMS['process_acceleration_std']**2,PARAMS['process_acceleration_std']**2,PARAMS['process_yaw_acceleration_std']**2])
            self.x=F@self.x;self.P=F@self.P@F.T+G@Q@G.T
        if zr is not None:
            dx,dy=self.x[:2]-own_pose[:2];q=max(float(dx*dx+dy*dy),PARAMS['minimum_distance_squared']);r=np.sqrt(q)
            H=np.zeros((2,6));H[0,:2]=[dx/r,dy/r];H[1,:2]=[-dy/q,dx/q]
            self.correct(zr,np.array([r,np.arctan2(dy,dx)-own_pose[2]]),H,self.Rr,True)
        if zg is not None:
            c,s=np.cos(self.x[4]),np.sin(self.x[4]);H=np.zeros((2,6));H[0,0]=H[1,1]=1.;H[0,4]=-self.a*s;H[1,4]=self.a*c
            self.correct(zg,self.x[:2]+self.a*np.array([c,s]),H,self.Rg)
        indices=[0,1,4];covariance=self.P[np.ix_(indices,indices)]
        return TargetPoseEstimate(float(self.x[0]),float(self.x[1]),float(np.arctan2(np.sin(self.x[4]),np.cos(self.x[4]))),covariance)
'''

PREDICTION = '''import numpy as np
PARAMS=__PARAMS__
class TargetPredictor:
    def __init__(self,projectile_speed_mps,armor_mounts):
        self.speed=projectile_speed_mps;self.mounts=armor_mounts;self.t=0.;self.history=np.empty((0,4))
    def update(self,observation,dt):
        self.t+=dt
        if observation.target_xy is None or (len(self.mounts) and observation.target_yaw_rad is None):return None
        time=self.t-observation.target_age_s
        if not len(self.history) or time>self.history[-1,0]:
            self.history=np.concatenate((self.history,np.array([[time,*observation.target_xy,observation.target_yaw_rad if observation.target_yaw_rad is not None else 0.]])))
        self.history=self.history[self.history[:,0]>=time-PARAMS['velocity_window_s']][-int(PARAMS['maximum_track_samples']):]
        if len(self.history)<int(PARAMS['minimum_track_samples']):return None
        times=self.history[:,0];u=times-times.mean();positions=self.history[:,1:3]
        velocity=(u[:,None]*(positions-positions.mean(axis=0))).sum(axis=0)/(u@u) if u@u else np.zeros(2)
        yaw_history=self.history[self.history[:,0]>=time-PARAMS['yaw_window_s']]
        angles=np.unwrap(yaw_history[:,3],period=PARAMS['yaw_period_rad']);v=yaw_history[:,0]-yaw_history[:,0].mean()
        rate=float(v@(angles-angles.mean())/(v@v)) if v@v else 0.
        center=observation.target_xy;own=observation.own_pose;flight=np.linalg.norm(center-own[:2])/self.speed
        point=center;best=None
        for _ in range(int(PARAMS['intercept_iterations'])):
            future_center=center+velocity*(observation.target_age_s+flight)
            if not len(self.mounts):
                point=future_center;flight=np.linalg.norm(point-own[:2])/self.speed
                continue
            yaw=observation.target_yaw_rad+rate*(observation.target_age_s+flight)
            c,s=np.cos(yaw),np.sin(yaw);R=np.array([[c,-s],[s,c]])
            points=future_center+self.mounts[:,:2]@R.T
            normals=np.column_stack((np.cos(yaw+self.mounts[:,2]),np.sin(yaw+self.mounts[:,2])))
            toward=own[:2]-points;score=np.sum(toward*normals,axis=1)/np.maximum(np.linalg.norm(toward,axis=1),np.sqrt(PARAMS['minimum_distance_squared']))
            best=int(np.argmax(score));point=points[best];flight=np.linalg.norm(point-own[:2])/self.speed
        if len(self.mounts) and score[best]<PARAMS['armor_facing_cosine']:return None
        delta=point-own[:2];bearing=np.arctan2(delta[1],delta[0])-own[2]
        return np.array([np.linalg.norm(delta),np.arctan2(np.sin(bearing),np.cos(bearing))],dtype=np.float64)
'''

CONTROL = '''import numpy as np
from tankbot import AimOutput
PARAMS=__PARAMS__
class AutoAim:
    def __init__(self,projectile_speed_mps,max_acceleration_radps2):
        self.limit=max_acceleration_radps2;self.previous=None
    def update(self,observation,dt):
        rt=observation.target_rt
        if rt is None:return AimOutput(float(np.clip(-PARAMS['kd']*observation.turret_rate_radps,-self.limit,self.limit)),False)
        bearing=rt[1];error=np.arctan2(np.sin(bearing-observation.turret_angle_rad),np.cos(bearing-observation.turret_angle_rad))
        rate=0. if self.previous is None else np.arctan2(np.sin(bearing-self.previous),np.cos(bearing-self.previous))/dt
        self.previous=bearing
        acceleration=float(np.clip(PARAMS['kp']*error+PARAMS['kd']*(rate-observation.turret_rate_radps),-self.limit,self.limit))
        future_error=error-observation.turret_rate_radps*PARAMS['control_delay_s']-.5*acceleration*PARAMS['control_delay_s']**2
        return AimOutput(acceleration,bool(abs(future_error)<PARAMS['fire_tolerance_rad'] and observation.weapon_ready))
'''


def solutions(config, kind="kalman"):
    from tankbot_host.workspace import starter
    files = starter(config)
    params = dict(config["validation"]["reference_aim"])
    params["control_delay_s"] = config["runtime"]["commit_delay_ticks"]/config["clock"]["physics_hz"]
    import math
    from armor_tracker_support import ARMOR
    definition=config["campaign"]["levels"][config["campaign"]["active_level"]]
    params["yaw_period_rad"]=next((metric["period_rad"] for metric in definition["evaluation"]["metrics"] if "period_rad" in metric),math.tau)
    for path,source in (("perception/armor_tracker.py",ARMOR),("perception/polar_tracker.py",POLAR),("perception/fusion_tracker.py",FUSION),
                        ("weapons/target_prediction.py",PREDICTION),("weapons/auto_aim.py",CONTROL)):
        files[path] = source.replace("__PARAMS__",repr(params))
    return files


class ManualAimHarness:
    """Player-view estimates and authorized self/weapon state only; acts through keyboard APIs."""
    def __init__(self, config):
        self.parameters = config["validation"]["reference_aim"]
        self.history = []

    def step(self, authority):
        estimate = authority._target_estimate
        if estimate is None:
            return
        message = estimate["payload"]
        tick = estimate["simulation_tick"]
        point = np.array([message["x_m"],message["y_m"]],dtype=np.float64)
        own = authority._sensors["/robot/localization/pose"]["payload"]
        xy = np.array([own["x_m"],own["y_m"]],dtype=np.float64)
        if authority.campaign.definition["armor_mode"]:
            yaw = message["yaw_rad"]
            from tankbot_host.chassis_profiles import target_geometry
            body=target_geometry(authority.config)["body"]
            length,width = body["length_m"],body["width_m"]
            mounts = np.array([[length/2,0],[-length/2,0],[0,width/2],[0,-width/2]])
            c,s = math.cos(yaw),math.sin(yaw)
            rotation = np.array([[c,-s],[s,c]])
            points = point+mounts@rotation.T
            normals = (mounts/np.linalg.norm(mounts,axis=1)[:,None])@rotation.T
            toward = xy-points
            index = int(np.argmax(np.sum(toward*normals,axis=1)/np.linalg.norm(toward,axis=1)))
            point = points[index]
        if not self.history or self.history[-1][0]!=tick:
            self.history.append((tick,point))
            cutoff=tick-authority.hz*self.parameters["velocity_window_s"]
            self.history=[sample for sample in self.history if sample[0]>=cutoff][-int(self.parameters["maximum_track_samples"]):]
        velocity = np.zeros(2)
        if len(self.history)>1:
            first_tick,first=self.history[0]
            velocity=(point-first)/((tick-first_tick)/authority.hz)
        flight=np.linalg.norm(point-xy)/authority.config["weapons"]["projectile"]["relative_speed_mps"]
        point=point+velocity*(flight+(authority.tick-tick)/authority.hz)
        desired=math.atan2(point[1]-xy[1],point[0]-xy[0])
        turret=authority._sensors["/robot/turret/joint_states"]["payload"]["position"][0]
        error=(desired-own["yaw_rad"]-turret+math.pi)%math.tau-math.pi
        limit=self.parameters["manual_aim_rate_radps"]
        authority.turret_keyboard({"velocity_radps":max(-limit,min(limit,self.parameters["manual_aim_gain_per_s"]*error))})
        if abs(error)<self.parameters["fire_tolerance_rad"] and authority._sensors["/robot/weapons/cannon/state"]["payload"]["ready"]:
            authority.fire_keyboard({"request_id":f'manual-{authority.tick}'})
