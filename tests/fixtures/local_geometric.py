"""Verification-only stateful geometric gap/rejoin controller; no search/trajectory window."""
import numpy as np
from tankbot import Twist,Vector3


class LocalController:
    def __init__(self,model,robot_radius_m,safety_margin_m,max_vx_mps,max_wz_radps,command_delay_s):
        self.model=model;self.radius=robot_radius_m+safety_margin_m
        self.max_v=max_vx_mps;self.max_w=max_wz_radps;self.delay=command_delay_s
        self.side=0;self.heading=None

    def update(self,o,dt):
        pose=o.estimated_pose;xy=pose[:2];yaw=pose[2];path=o.reference_path
        if np.linalg.norm(path[-1]-xy)<.35:return o.nominal_command
        scan=o.scan;angles=np.arctan2(np.sin(scan.angles_rad),np.cos(scan.angles_rad))
        points=scan.ranges_m[scan.hit_mask,None]*np.column_stack((np.cos(angles[scan.hit_mask]),np.sin(angles[scan.hit_mask])))
        near=int(np.argmin(np.linalg.norm(path-xy,axis=1)));index=near;length=0.
        while index+1<len(path) and length<1.3:
            length+=np.linalg.norm(path[index+1]-path[index]);index+=1
        delta=path[index]-xy
        desired=float(np.arctan2(np.sin(np.arctan2(delta[1],delta[0])-yaw),np.cos(np.arctan2(delta[1],delta[0])-yaw)))
        candidates=np.linspace(-np.pi,np.pi,145)
        directions=np.column_stack((np.cos(candidates),np.sin(candidates)))
        if len(points):
            along=points@directions.T
            across=np.abs(points[:,0,None]*directions[None,:,1]-points[:,1,None]*directions[None,:,0])
            radius=self.radius+.07
            reaches=np.where((along>0)&(across<radius),along-np.sqrt(np.maximum(0.,radius*radius-across*across)),6.)
            free=np.maximum(0.,reaches.min(axis=0))
        else:free=np.full(len(candidates),6.)
        angular_error=np.arctan2(np.sin(candidates-desired),np.cos(candidates-desired))
        desired_index=int(np.argmin(np.abs(angular_error)))
        obstructed=free[desired_index]<1.15
        if not obstructed and self.side and free[desired_index]>1.7:self.side=0
        viable=free>1.05
        penalty=np.abs(angular_error)+.06/(free+.1)
        if self.heading is not None:
            previous=np.arctan2(np.sin(self.heading-yaw),np.cos(self.heading-yaw))
            penalty+=.22*np.abs(np.arctan2(np.sin(candidates-previous),np.cos(candidates-previous)))
        if self.side:
            relative=np.arctan2(np.sin(candidates-desired),np.cos(candidates-desired))
            penalty+=np.where(relative*self.side<-.05,1.5,0.)
        penalty[~viable]=1e6
        choice=int(np.argmin(penalty))
        angle=float(candidates[choice]);self.heading=yaw+angle
        if obstructed and self.side==0:self.side=1 if angle-desired>0 else -1
        if not viable[choice]:return Twist(angular=Vector3(z=float(self.side or 1)*.6))
        wz=float(np.clip(2.*angle,-self.max_w,self.max_w))
        rates=o.wheel_rates_radps*self.model.wheel_radius_m
        vnow=float(np.mean(rates))
        delay=self.delay+o.scan_age_s
        # Conservative geometric corridor + delay-aware forward clearance.
        clearance=free[int(np.argmin(np.abs(candidates)))]
        braking=max(0.,clearance-max(vnow,0.)*delay-.18)
        v=min(.35,max(0.,.8*braking))/(1+2*abs(angle)) if abs(angle)<.65 else 0.
        return Twist(Vector3(x=float(v)),Vector3(z=wz))
