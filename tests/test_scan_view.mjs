import test from 'node:test';
import assert from 'node:assert/strict';
import {ScanHistory} from '../web/scan-view.js';
const profile={campaign:{active_level:'arbitrary',levels:[{level_id:'arbitrary',allowed_layers:['scan','scan_points'],visualization:{scan_view:{history_ticks:60,history_samples:4,fresh_ticks:12}}}]}};
function view(tick,poseTick,scanTick=6,revision=0,source='ekf',run='run'){
 const envelope={run_id:run,simulation_tick:scanTick,frame_id:'base_link',schema:'scan2d@1',payload:{sample_tick:scanTick,ranges_m:[1],hit_mask:[true],angle_min_rad:0,angle_increment_rad:1,range_max_m:6}};
 return {run_id:run,simulation_tick:tick,payload:{view_revision:revision,selected_pose:{source_id:source},local_observations:[envelope],pose_estimates:poseTick==null?[]:[{run_id:run,simulation_tick:poseTick,frame_id:'map',channel:`/robot/estimates/${source}/pose`,payload:{x_m:2,y_m:3,yaw_rad:Math.PI/2,child_frame_id:'base_link'}}]}};
}
test('scan map projection requires exact sample tick and waits for late player EKF',()=>{
 const h=new ScanHistory(profile);h.update(view(6,0));assert.deepEqual(h.bodyPoints(),[[1,0]]);assert.deepEqual(h.mapPoints(),[]);
 h.update(view(12,6,12));assert.deepEqual(h.mapPoints(),[[2,4]]);assert.equal(h.projectedTick,6);
 h.update(view(18,12,12));assert.deepEqual(h.mapPoints(),[[2,4]]);
 h.update(view(25,12,12));assert.deepEqual(h.mapPoints(),[]);
});
test('run/revision/source/frame and history bounds cannot carry old scan projection',()=>{
 const h=new ScanHistory(profile);h.update(view(12,6));assert.equal(h.mapPoints().length,1);
 for(const value of [view(12,null,6,1),view(12,null,6,2,'other'),view(12,null,6,3,'ekf','new')]){h.update(value);assert.deepEqual(h.mapPoints(),[]);}
 const frame=view(12,6,6,4);frame.payload.pose_estimates[0].frame_id='odom';h.update(frame);assert.deepEqual(h.mapPoints(),[]);
 h.update(view(12,6,6,5,'system'));assert.deepEqual(h.mapPoints(),[]);
 for(let tick=20;tick<80;tick++)h.update(view(tick,tick,tick,6));assert.ok(h.poses.size<=4);
});
test('no map projection grant prevents display even if body scan is authorized',()=>{
 const p=structuredClone(profile);p.campaign.levels[0].allowed_layers=['scan'];const h=new ScanHistory(p);h.update(view(12,6));assert.equal(h.bodyPoints().length,1);assert.deepEqual(h.mapPoints(),[]);
});
