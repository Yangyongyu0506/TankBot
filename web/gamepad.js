// Browser input adapter only: no simulation state, world handles or runtime permissions.
const clamp=(value,min=-1,max=1)=>Math.max(min,Math.min(max,value));
export const neutralControls=()=>({vx:0,vy:0,wz:0,turret:0});
export const moving=controls=>Boolean(controls.vx||controls.vy||controls.wz||controls.turret);

export function radialDeadzone(x,y,deadzone){
  const length=Math.hypot(x,y);
  if(length<=deadzone)return [0,0];
  const scale=Math.min(1,(length-deadzone)/(1-deadzone))/length;
  return [x*scale,y*scale];
}
function axialDeadzone(value,deadzone){
  return Math.abs(value)<=deadzone?0:Math.sign(value)*(Math.abs(value)-deadzone)/(1-deadzone);
}

export function mapGamepad(pad,config,chassis){
  if(!pad?.connected||(config.standard_mapping_only&&pad.mapping!=="standard"))return null;
  const axes={};
  for(const [name,binding] of Object.entries(config.axes)){
    const value=pad.axes?.[binding.index];
    if(!Number.isFinite(value))return null;
    axes[name]=clamp(value)*binding.sign;
  }
  const buttons={};
  for(const [name,index] of Object.entries(config.buttons)){
    const button=pad.buttons?.[index];
    if(!button||!Number.isFinite(button.value))return null;
    buttons[name]=button.value>=config.button_threshold;
  }
  const [horizontal,forward]=radialDeadzone(axes.horizontal,axes.forward,config.deadzone);
  const yawButtons=Number(buttons.yaw_left)-Number(buttons.yaw_right);
  return {
    vx:forward*config.linear_mps,
    vy:chassis==="omnidirectional"?horizontal*config.linear_mps:0,
    wz:clamp((chassis==="omnidirectional"?0:horizontal)+yawButtons)*config.yaw_radps,
    turret:axialDeadzone(axes.turret,config.deadzone)*config.turret_radps,
    fire:buttons.fire,editor:buttons.editor,
    centered:horizontal===0&&forward===0&&axialDeadzone(axes.turret,config.deadzone)===0&&!Object.values(buttons).some(Boolean),
  };
}

export class GamepadDriver {
  constructor(config,chassis){
    this.config=config;this.chassis=chassis;this.enabled=Boolean(config?.enabled);
    this.preferred=null;this.identity=null;this.index=null;
    this.suspend(true);
  }
  suspend(ui=false){this.armed=false;if(ui){this.uiArmed=false;this.previousEditor=false;}}
  select(index){this.preferred=index;this.identity=null;this.suspend(true);}
  setEnabled(enabled){this.enabled=enabled;this.identity=null;this.suspend(true);}
  sample(pads,{motionAllowed=true,uiAllowed=true}={}){
    const devices=Array.from(pads??[]).filter(pad=>pad?.connected);
    const result={...neutralControls(),fire:false,editor:false,devices,status:"waiting",device:null};
    if(!this.enabled){this.suspend(true);return {...result,status:"disabled"};}
    const compatible=pad=>mapGamepad(pad,this.config,this.chassis)!==null;
    const pad=this.preferred!==null?devices.find(pad=>pad.index===this.preferred):
      devices.find(pad=>pad.index===this.index&&compatible(pad))??devices.find(compatible)??devices[0];
    if(!pad){this.identity=null;this.suspend(true);return result;}
    result.device=pad;
    const identity=JSON.stringify([pad.index,pad.id]);
    if(identity!==this.identity){this.identity=identity;this.index=pad.index;this.suspend(true);}
    const mapped=mapGamepad(pad,this.config,this.chassis);
    if(!mapped){this.suspend(true);return {...result,status:"unsupported"};}
    if(!uiAllowed){this.suspend(true);return {...result,status:"paused"};}
    if(!this.uiArmed){
      if(mapped.centered)this.uiArmed=true;
      this.previousEditor=mapped.editor;
    }else{
      result.editor=mapped.editor&&!this.previousEditor;
      this.previousEditor=mapped.editor;
    }
    if(!motionAllowed){this.suspend();this.previousFire=mapped.fire;return {...result,status:"paused"};}
    if(!this.armed){
      this.previousFire=mapped.fire;
      if(!mapped.centered)return {...result,status:"neutral"};
      this.armed=true;
    }
    result.fire=mapped.fire&&!this.previousFire;
    this.previousFire=mapped.fire;
    return {...result,vx:mapped.vx,vy:mapped.vy,wz:mapped.wz,turret:mapped.turret,status:"ready"};
  }
}

export function manualTargets(profile,keys,pad=neutralControls(),allowed=true){
  const axis=(a,b)=>Number(keys.has(a))-Number(keys.has(b));
  const chassisKeys=["KeyW","KeyS","KeyA","KeyD","KeyQ","KeyE"].some(key=>keys.has(key));
  const turretKeys=keys.has("KeyJ")||keys.has("KeyL"),omni=profile.chassis==="omnidirectional";
  const controls=!allowed?neutralControls():{
    vx:chassisKeys?axis("KeyW","KeyS")*profile.view.keyboard_linear_mps:pad.vx,
    vy:omni?(chassisKeys?axis("KeyA","KeyD")*profile.view.keyboard_linear_mps:pad.vy):0,
    wz:chassisKeys?(omni?axis("KeyQ","KeyE"):axis("KeyA","KeyD"))*profile.view.keyboard_yaw_radps:pad.wz,
    turret:turretKeys?axis("KeyJ","KeyL")*profile.view.keyboard_turret_radps:pad.turret,
  };
  return {twist:{linear:{x:controls.vx,y:controls.vy,z:0},angular:{x:0,y:0,z:controls.wz}},
    turret:{velocity_radps:controls.turret},active:moving(controls)};
}
