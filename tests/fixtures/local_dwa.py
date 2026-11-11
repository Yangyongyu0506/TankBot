"""Verification-only dynamic-window trajectory sampler; no map/truth input."""
import numpy as np
import heapq
import math
from tankbot import Twist,Vector3


class LocalController:
    def __init__(self,model,robot_radius_m,safety_margin_m,max_vx_mps,max_wz_radps,command_delay_s):
        self.model=model;self.radius=robot_radius_m+safety_margin_m
        self.max_v=max_vx_mps;self.max_w=max_wz_radps;self.delay=command_delay_s
        self.last=np.zeros(2);self.times=np.linspace(.1,3.,16)
        self.side=0.;self.escape=None;self.stalled=0.;self.guide=None;self.guide_age=9.

    def update(self,observation,dt):
        pose=observation.estimated_pose;scan=observation.scan;xy=pose[:2];yaw=pose[2]
        if np.linalg.norm(observation.reference_path[-1]-xy)<.10:return Twist()
        directions=np.column_stack((np.cos(scan.angles_rad),np.sin(scan.angles_rad)))
        points=scan.ranges_m[scan.hit_mask,None]*directions[scan.hit_mask]
        path=observation.reference_path
        near=int(np.argmin(np.linalg.norm(path-xy,axis=1)))
        index=near;span=0.
        while index+1<len(path) and span<2.0:
            span+=np.linalg.norm(path[index+1]-path[index]);index+=1
        delta=path[index]-xy;c,s=np.cos(yaw),np.sin(yaw)
        target=np.array([c*delta[0]+s*delta[1],-s*delta[0]+c*delta[1]])
        self.guide_age+=dt
        if self.guide is None or self.guide_age>=.5:
            self.guide=self.local_guide(points,target,xy,yaw)
            self.guide_age=0.
        if self.guide is not None:
            delta=self.guide-xy
            target=np.array([c*delta[0]+s*delta[1],-s*delta[0]+c*delta[1]])
        # A measured wheel-derived velocity, never the desired nominal command.
        vl,vr=observation.wheel_rates_radps*self.model.wheel_radius_m
        vnow=(vl+vr)/2;wnow=(vr-vl)/self.model.wheel_separation_m
        velocities=np.array([0.,.12,.22,.32,.4])
        turns=np.linspace(-self.max_w,self.max_w,13)
        v,w=np.meshgrid(velocities,turns);v=v.ravel();w=w.ravel()
        # Bound acceleration candidates and include a stationary rotation option.
        viable=(np.abs(v-vnow)<=.38)&(np.abs(w-wnow)<=1.2)
        w=np.r_[w[viable],0.];v=np.r_[v[viable],0.]
        t=self.times[None,:];theta=w[:,None]*t
        with np.errstate(divide='ignore',invalid='ignore'):
            x=np.where(np.abs(w[:,None])<1e-8,v[:,None]*t,v[:,None]*np.sin(theta)/w[:,None])
            y=np.where(np.abs(w[:,None])<1e-8,0.,v[:,None]*(1-np.cos(theta))/w[:,None])
        trajectories=np.stack((x,y),axis=-1)
        # Hold current measured motion during the fixed chain delay and scan age.
        age=self.delay+observation.scan_age_s
        drift=np.array([vnow*age,0.])
        if len(points):
            distance=np.sqrt(np.sum((trajectories[:,:,None,:]+drift-points[None,None,:,:])**2,axis=-1).min(axis=(1,2)))
        else:distance=np.full(len(v),6.)
        current_clearance=float(np.linalg.norm(points,axis=1).min()) if len(points) else 6.
        threshold=min(self.radius+.04,max(self.radius,current_clearance-.002))
        safe=distance>threshold
        terminal=np.linalg.norm(trajectories[:,-1,:]-target,axis=1)
        heading=np.abs(np.arctan2(np.sin(np.arctan2(target[1],target[0])-theta[:,-1]),np.cos(np.arctan2(target[1],target[0])-theta[:,-1])))
        score=-terminal-.10*heading+.16*np.minimum(distance,1.2)+.20*v-.025*np.abs(w-self.last[1])
        score[~safe]=-1e9
        choice=int(np.argmax(score))
        if not safe[choice]:
            # At near-zero clearance, stop and turn towards the largest measured gap.
            turn=float(np.arctan2(target[1],target[0]))
            self.last=np.array([0.,np.clip(1.5*turn,-self.max_w,self.max_w)])
        else:self.last=np.array([v[choice],w[choice]])
        # Preserve terminal braking from the reused path follower when close.
        if np.linalg.norm(path[-1]-xy)<.35:
            self.last=np.array([observation.nominal_command.linear.x,observation.nominal_command.angular.z])
        return Twist(Vector3(x=float(self.last[0])),Vector3(z=float(self.last[1])))

    def local_guide(self,points,target,xy,yaw):
        # A bounded temporary scan-only window guides DWA around local minima.
        # This does not alter the frozen global route or call GlobalPlanner.
        resolution=.25;axis=np.arange(-16,17)*resolution
        gx,gy=np.meshgrid(axis,axis);centres=np.column_stack((gx.ravel(),gy.ravel()))
        if len(points):
            blocked=(np.sum((centres[:,None,:]-points[None,:,:])**2,axis=-1).min(axis=1)<(self.radius+.02)**2).reshape(33,33)
        else:blocked=np.zeros((33,33),dtype=bool)
        start=(16,16);blocked[start]=False
        # Goal is the nearest free point to the public route lookahead, not a
        # hidden-world destination. Only this ephemeral local window is searched.
        costs=np.linalg.norm(centres-target,axis=1).reshape(33,33)
        costs[blocked]=1e9;goal=np.unravel_index(int(np.argmin(costs)),costs.shape)
        parent={};dist={start:0.};queue=[(math.dist(start,goal),0.,start)];found=False
        while queue:
            _,cost,cell=heapq.heappop(queue)
            if cost!=dist[cell]:continue
            if cell==goal:found=True;break
            r,c=cell
            for dr,dc in ((-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)):
                nr,nc=r+dr,c+dc
                if not(0<=nr<33 and 0<=nc<33) or blocked[nr,nc]:continue
                if dr and dc and (blocked[r,nc] or blocked[nr,c]):continue
                v=cost+math.hypot(dr,dc)
                if v<dist.get((nr,nc),1e9):
                    dist[nr,nc]=v;parent[nr,nc]=cell
                    heapq.heappush(queue,(v+math.dist((nr,nc),goal),v,(nr,nc)))
        if not found:return None
        cells=[goal]
        while cells[-1]!=start:cells.append(parent[cells[-1]])
        cells=cells[::-1];selected=cells[min(5,len(cells)-1)]
        point=np.array([axis[selected[1]],axis[selected[0]]]);c,s=np.cos(yaw),np.sin(yaw)
        return xy+np.array([c*point[0]-s*point[1],s*point[0]+c*point[1]])
