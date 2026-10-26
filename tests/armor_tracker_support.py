"""Acceptance-only anonymous armor EKF; uses observations and public geometry only."""
ARMOR = '''import numpy as np
from tankbot import TargetPoseEstimate
PARAMS=__PARAMS__
class ArmorTracker:
    def __init__(self,armor_mounts,measurement_covariance):
        self.mounts=armor_mounts;self.R=measurement_covariance;self.x=None;self.P=np.eye(6)*PARAMS['initial_variance']
    def predicted(self,own):
        yaw=self.x[4];c,s=np.cos(yaw),np.sin(yaw);rotation=np.array([[c,-s],[s,c]])
        points=self.x[:2]+self.mounts[:,:2]@rotation.T
        delta=points-own[:2];q=np.maximum(np.sum(delta*delta,axis=1),PARAMS['minimum_distance_squared'])
        predicted=np.column_stack((np.sqrt(q),np.arctan2(delta[:,1],delta[:,0])-own[2]))
        predicted[:,1]=np.arctan2(np.sin(predicted[:,1]),np.cos(predicted[:,1]))
        return points,delta,q,predicted
    def update(self,measurements_rt,own_pose,dt):
        z=measurements_rt
        if self.x is None:
            if len(z)<2:return None
            points=own_pose[:2]+z[:,0,None]*np.column_stack((np.cos(z[:,1]+own_pose[2]),np.sin(z[:,1]+own_pose[2])))
            midpoint=points.mean(axis=0);d=points[1]-points[0];length=np.linalg.norm(d)
            if length<=np.sqrt(PARAMS['minimum_distance_squared']):return None
            radius=np.linalg.norm(self.mounts[0,:2]);height=np.sqrt(max(0.,radius*radius-length*length/4))
            perpendicular=np.array([-d[1],d[0]])/length
            centers=np.array([midpoint+height*perpendicular,midpoint-height*perpendicular])
            center=centers[np.argmax(np.linalg.norm(centers-own_pose[:2],axis=1))]
            phase=np.arctan2(points[0,1]-center[1],points[0,0]-center[0])
            self.x=np.array([center[0],center[1],0.,0.,phase,0.])
        else:
            F=np.eye(6);F[0,2]=F[1,3]=F[4,5]=dt
            G=np.zeros((6,3));G[0,0]=G[1,1]=G[4,2]=dt*dt/2;G[2,0]=G[3,1]=G[5,2]=dt
            Q=np.diag([PARAMS['process_acceleration_std']**2,PARAMS['process_acceleration_std']**2,PARAMS['process_yaw_acceleration_std']**2])
            self.x=F@self.x;self.P=F@self.P@F.T+G@Q@G.T
        if len(z):
            _,_,_,predicted=self.predicted(own_pose)
            residual=z[:,None,:]-predicted[None,:,:]
            residual[:,:,1]=np.arctan2(np.sin(residual[:,:,1]),np.cos(residual[:,:,1]))
            cost=np.sum(residual*residual/np.diag(self.R),axis=2)
            choices=[(i,) for i in range(4)] if len(z)==1 else [(i,j) for i in range(4) for j in range(4) if i!=j]
            association=min(choices,key=lambda ids:sum(cost[row,index] for row,index in enumerate(ids)))
            for measured,index in zip(z,association):
                points,delta,q,predicted=self.predicted(own_pose);dx,dy=delta[index];r=np.sqrt(q[index])
                derivative=np.array([-(points[index,1]-self.x[1]),points[index,0]-self.x[0]])
                Hxy=np.array([[dx/r,dy/r],[-dy/q[index],dx/q[index]]])
                H=np.zeros((2,6));H[:,:2]=Hxy;H[:,4]=Hxy@derivative
                innovation=measured-predicted[index];innovation[1]=np.arctan2(np.sin(innovation[1]),np.cos(innovation[1]))
                K=np.linalg.solve((H@self.P@H.T+self.R).T,(self.P@H.T).T).T
                self.x+=K@innovation;A=np.eye(6)-K@H;self.P=A@self.P@A.T+K@self.R@K.T
        yaw=np.arctan2(np.sin(self.x[4]),np.cos(self.x[4]));indices=[0,1,4]
        return TargetPoseEstimate(float(self.x[0]),float(self.x[1]),float(yaw),self.P[np.ix_(indices,indices)])
'''
