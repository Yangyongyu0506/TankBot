"""Acceptance-only numerical solutions. No target truth, patrol path or engine imports."""
import json

TRACKER = '''import numpy as np
from tankbot import TargetEstimate
PARAMS = __PARAMS__
class Tracker:
    def __init__(self):
        self.t=0.0; self.state=None; self.P=np.eye(4); self.velocity=np.zeros(2)
        self.history=np.empty((0,3)); self.kind=__KIND__
    def update(self, measurements, dt):
        self.t+=dt
        z=np.array([measurements[0].x_m,measurements[0].y_m]) if measurements else None
        if self.kind=='kalman':
            if self.state is None:
                if z is None:return None
                self.state=np.array([z[0],z[1],0.,0.]);self.P=np.eye(4)*PARAMS['initial_variance']
            else:
                F=np.eye(4);F[0,2]=dt;F[1,3]=dt
                G=np.array([[dt*dt/2,0],[0,dt*dt/2],[dt,0],[0,dt]])
                self.state=F@self.state;self.P=F@self.P@F.T+G@G.T*PARAMS['process_acceleration_std']**2
                if z is not None:
                    H=np.array([[1.,0,0,0],[0,1.,0,0]])
                    R=np.eye(2)*PARAMS['measurement_std_m']**2
                    K=np.linalg.solve((H@self.P@H.T+R).T,(self.P@H.T).T).T
                    self.state=self.state+K@(z-H@self.state)
                    A=np.eye(4)-K@H;self.P=A@self.P@A.T+K@R@K.T
            self.velocity=self.state[2:].copy();position=self.state[:2]
        else:
            if z is not None:
                self.history=np.concatenate((self.history,np.array([[self.t,z[0],z[1]]])))
            self.history=self.history[self.history[:,0]>=self.t-PARAMS['position_window_s']][-int(PARAMS['maximum_track_samples']):]
            if not len(self.history):return None
            times=self.history[:,0];positions=self.history[:,1:];u=times-times.mean()
            self.velocity=(u[:,None]*(positions-positions.mean(axis=0))).sum(axis=0)/(u@u) if u@u>0 else np.zeros(2)
            position=positions.mean(axis=0)+self.velocity*(self.t-times.mean())
        return TargetEstimate(float(position[0]),float(position[1]))
'''

POSE = '''import numpy as np
from tankbot import TargetEstimate,TargetPoseEstimate
from perception.tracker import Tracker
PARAMS=__PARAMS__
class PoseTracker:
    def __init__(self):self.tracker=Tracker();self.yaw=0.;self.initialized=False
    def update(self,measurements,dt):
        position=self.tracker.update(tuple(TargetEstimate(float(p[0]),float(p[1])) for p in measurements),dt)
        if position is None:return None
        velocity=self.tracker.velocity
        if np.linalg.norm(velocity)>=PARAMS['yaw_speed_threshold_mps']:
            angle=float(np.arctan2(velocity[1],velocity[0]))
            difference=np.arctan2(np.sin(angle-self.yaw),np.cos(angle-self.yaw))
            self.yaw=angle if not self.initialized else self.yaw+PARAMS['yaw_alpha']*difference
            self.initialized=True
        return TargetPoseEstimate(position.x_m,position.y_m,float(np.arctan2(np.sin(self.yaw),np.cos(self.yaw))))
'''

AIM = '''import numpy as np
from tankbot import AimOutput
PARAMS=__PARAMS__
class AutoAim:
    def __init__(self,projectile_speed_mps,max_acceleration_radps2):
        self.speed=projectile_speed_mps;self.limit=max_acceleration_radps2;self.t=0.;self.history=np.empty((0,3));self.previous_pose=None
    def update(self,observation,dt):
        self.t+=dt
        if observation.target_xy is None:return AimOutput(0.,False)
        point=observation.target_xy
        self.history=np.concatenate((self.history,np.array([[self.t-observation.target_age_s,point[0],point[1]]])))
        self.history=self.history[self.history[:,0]>=self.t-PARAMS['velocity_window_s']-observation.target_age_s][-int(PARAMS['maximum_track_samples']):]
        times=self.history[:,0];points=self.history[:,1:];u=times-times.mean()
        velocity=(u[:,None]*(points-points.mean(axis=0))).sum(axis=0)/(u@u) if u@u>0 else np.zeros(2)
        speed=np.linalg.norm(velocity)
        if speed>PARAMS['max_target_speed_mps']:velocity*=PARAMS['max_target_speed_mps']/speed
        own=observation.own_pose
        own_velocity=np.zeros(2) if self.previous_pose is None else (own[:2]-self.previous_pose[:2])/dt
        own_rate=0. if self.previous_pose is None else np.arctan2(np.sin(own[2]-self.previous_pose[2]),np.cos(own[2]-self.previous_pose[2]))/dt
        self.previous_pose=own.copy()
        age=observation.target_age_s
        flight=np.linalg.norm(point-own[:2])/self.speed
        for _ in range(int(PARAMS['intercept_iterations'])):
            predicted=point+velocity*(age+flight)
            flight=np.linalg.norm(predicted-own[:2])/self.speed
        relative=predicted-own[:2]
        desired=np.arctan2(relative[1],relative[0])
        error=np.arctan2(np.sin(desired-own[2]-observation.turret_angle_rad),np.cos(desired-own[2]-observation.turret_angle_rad))
        rv=velocity-own_velocity
        desired_rate=(relative[0]*rv[1]-relative[1]*rv[0])/max(float(relative@relative),PARAMS['minimum_distance_squared'])-own_rate
        acceleration=float(np.clip(PARAMS['kp']*error+PARAMS['kd']*(desired_rate-observation.turret_rate_radps),-self.limit,self.limit))
        future_error=error-observation.turret_rate_radps*PARAMS['control_delay_s']-.5*acceleration*PARAMS['control_delay_s']**2
        reliable=len(times)>=int(PARAMS['minimum_track_samples']) and times[-1]-times[0]>=PARAMS['minimum_fit_span_s']
        return AimOutput(acceleration,bool(reliable and abs(future_error)<PARAMS['fire_tolerance_rad'] and observation.weapon_ready))
'''

ARMOR = '''import numpy as np
from tankbot import AimInput,AimOutput
from weapons.auto_aim import AutoAim
PARAMS=__PARAMS__
class ArmorAim:
    def __init__(self,projectile_speed_mps,max_acceleration_radps2,armor_mounts):
        self.controller=AutoAim(projectile_speed_mps,max_acceleration_radps2);self.mounts=armor_mounts;self.index=None
    def update(self,observation,dt):
        if observation.target_xy is None or observation.target_yaw_rad is None:return AimOutput(0.,False)
        yaw=observation.target_yaw_rad;c=np.cos(yaw);s=np.sin(yaw)
        R=np.array([[c,-s],[s,c]])
        points=observation.target_xy+self.mounts[:,:2]@R.T
        normals=np.column_stack((np.cos(yaw+self.mounts[:,2]),np.sin(yaw+self.mounts[:,2])))
        direction=observation.own_pose[:2]-points
        score=np.sum(normals*direction,axis=1)/np.linalg.norm(direction,axis=1)
        index=int(np.argmax(score))
        if self.index!=index:self.controller.history=np.empty((0,3));self.index=index
        value=AimInput(points[index],observation.target_age_s,observation.own_pose,observation.turret_angle_rad,observation.turret_rate_radps,observation.weapon_ready)
        result=self.controller.update(value,dt)
        return AimOutput(result.acceleration_radps2,bool(result.fire and score[index]>=PARAMS['armor_facing_cosine']))
'''


def solutions(config, kind="kalman"):
    from tankbot_host.workspace import starter
    from campaign_support import TRANSFORMS
    files=starter(config)
    params=dict(config["validation"]["reference_aim"])
    params["control_delay_s"]=config["runtime"]["commit_delay_ticks"]/config["clock"]["physics_hz"]
    def source(template):return template.replace("__PARAMS__",repr(params)).replace("__KIND__",repr(kind))
    files.update({"perception/transforms.py":TRANSFORMS,"perception/tracker.py":source(TRACKER),"perception/pose_tracker.py":source(POSE),
                  "weapons/auto_aim.py":source(AIM),"weapons/armor_aim.py":source(ARMOR)})
    return files
