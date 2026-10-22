// Presentation uses only authorized view samples. No physics, collision or future extrapolation.
export const lerp = (a, b, t) => a + (b - a) * t;
const shortAngle = a => Math.atan2(Math.sin(a), Math.cos(a));
const timeOf = (tick, hz) => tick * 1000 / hz;

function bracket(samples, time) {
  if (!samples.length) return null;
  if (time <= samples[0].time) return [samples[0], samples[0], 0];
  for (let i = 1; i < samples.length; i++) {
    if (time < samples[i].time) {
      const a = samples[i - 1], b = samples[i];
      return [a, b, (time - a.time) / (b.time - a.time)];
    }
  }
  const last = samples.at(-1);
  return [last, last, 0];
}

function putSample(samples, sample) {
  const last = samples.at(-1);
  if (!last || sample.time > last.time) samples.push(sample);
  else if (sample.time === last.time) samples[samples.length - 1] = sample;
}

export class SceneTimeline {
  constructor(physicsHz, options, jumpDistance) {
    this.hz = physicsHz;
    this.options = options;
    this.jumpDistance = jumpDistance;
    this.clear();
  }

  clear() {
    this.frames = [];
    this.poses = [];
    this.turrets = [];
    this.latest = null;
    this.context = null;
    this.renderTime = -Infinity;
  }

  push(message, receivedMs) {
    if (this.latest && message.run_id === this.latest.run_id &&
        (message.sequence_number <= this.latest.sequence_number ||
         message.payload.view_revision < this.latest.payload.view_revision ||
         message.simulation_tick < this.latest.simulation_tick)) return {accepted: false};
    const selected = message.payload.selected_pose;
    const context = [message.run_id, message.payload.view_revision, selected?.source_id, selected?.frame_id].join(":");
    const reset = context !== this.context;
    // Losing an estimate hides the robot immediately; it cannot reveal a true camera target.
    const clearCamera = this.latest && (message.run_id !== this.latest.run_id ||
      message.payload.view_revision !== this.latest.payload.view_revision ||
      (selected && this.latest.payload.selected_pose && context !== this.context));
    if (reset) this.clear();
    this.context = context;
    this.latest = message;
    this.receivedMs = receivedMs;
    const time = timeOf(message.simulation_tick, this.hz);
    putSample(this.frames, {time, payload: message.payload});
    let poseJump = false;
    if (selected) {
      const sample = {time: timeOf(selected.simulation_tick, this.hz), pose: selected.pose};
      const old = this.poses.at(-1);
      poseJump = old && Math.hypot(sample.pose.x_m - old.pose.x_m, sample.pose.y_m - old.pose.y_m) > this.jumpDistance;
      if (poseJump) this.poses = [];
      putSample(this.poses, sample);
    }
    const joint = message.payload.local_observations.find(m => m.channel === "/robot/turret/joint_states");
    if (joint) putSample(this.turrets, {time: timeOf(joint.simulation_tick, this.hz), angle: joint.payload.position[0]});
    const cutoff = time - this.options.history_ms;
    for (const samples of [this.frames, this.poses, this.turrets]) {
      // Keep one lower endpoint, including a stale pose that is still authorized.
      while (samples.length > 2 && samples[1].time < cutoff) samples.shift();
    }
    return {accepted: true, reset, clearCamera, poseJump};
  }

  sample(nowMs) {
    if (!this.latest) return {pose: null, objects: [], turretAngle: 0};
    const selected = this.latest.payload.selected_pose;
    const delay = selected && selected.source_id !== "system"
      ? this.options.estimate_interpolation_delay_ms : this.options.interpolation_delay_ms;
    const newestTime = timeOf(this.latest.simulation_tick, this.hz);
    // A stalled stream holds the last received state. It never predicts hidden events.
    const target = Math.min(newestTime, newestTime + Math.max(0, nowMs - this.receivedMs) - delay);
    this.renderTime = Math.min(newestTime, Math.max(this.renderTime, target));
    const [a, b, alpha] = bracket(this.frames, this.renderTime);
    const nextObjects = new Map(b.payload.objects.map(o => [`${o.kind}:${o.projectile_id ?? o.target_id}`, o]));
    const objects = a.payload.objects.map(o => {
      const next = nextObjects.get(`${o.kind}:${o.projectile_id ?? o.target_id}`);
      if (o.kind !== "projectile" || !next) return {...o};
      return {...o, x_m: lerp(o.x_m, next.x_m, alpha), y_m: lerp(o.y_m, next.y_m, alpha)};
    });
    let pose = null;
    const pair = bracket(this.poses, this.renderTime);
    if (selected && pair) {
      const [p, q, t] = pair;
      pose = {x_m: lerp(p.pose.x_m, q.pose.x_m, t), y_m: lerp(p.pose.y_m, q.pose.y_m, t),
        yaw_rad: p.pose.yaw_rad + shortAngle(q.pose.yaw_rad - p.pose.yaw_rad) * t,
        stale: selected.freshness === "stale"};
    }
    const joints = bracket(this.turrets, this.renderTime);
    // Joint angle is continuous/unwrapped; short-angle interpolation would lose turns.
    const turretAngle = joints ? lerp(joints[0].angle, joints[1].angle, joints[2]) : 0;
    return {pose, objects, turretAngle, simulationTimeMs: this.renderTime};
  }
}

export class FollowCamera {
  constructor(origin) { this.origin = origin; this.reset(); }
  reset() { [this.x, this.y] = this.origin; }
  follow(pose) { if (pose) { this.x = pose.x_m; this.y = pose.y_m; } }
  project(x, y, width, height, viewportWidth) {
    const scale = width / viewportWidth;
    return [width / 2 + (x - this.x) * scale, height / 2 - (y - this.y) * scale];
  }
}

function plate(ctx, x, y, length, width, radius, fill, stroke) {
  ctx.fillStyle = fill;
  ctx.strokeStyle = stroke;
  ctx.beginPath();
  ctx.roundRect(x - length / 2, y - width / 2, length, width, radius);
  ctx.fill();
  ctx.stroke();
}

// Positive wheel axes point inward; wheel rolling direction is CCW tangent.
export function omniMounts(calibration) {
  if (calibration?.geometry_version !== "radial_omni@1") throw new Error("Unsupported omni calibration");
  return calibration.wheels.map(w => {
    const angle = w.azimuth_deg * Math.PI / 180;
    return {name: w.name, x_m: calibration.center_radius_m * Math.cos(angle),
      y_m: calibration.center_radius_m * Math.sin(angle), drive_yaw_rad: angle + Math.PI / 2};
  });
}

export function drawChassis(ctx, model, scale, stale = false, calibration = null) {
  const colors = model.colors;
  const shell = stale ? colors.stale : colors.shell;
  ctx.lineWidth = 1;
  if (model.kind === "tracked") {
    const track = model.track;
    for (const side of [-1, 1]) {
      const y = side * track.center_y_m * scale;
      plate(ctx, 0, y, track.length_m * scale, track.width_m * scale, track.radius_m * scale, colors.rubber, colors.edge);
      ctx.strokeStyle = colors.roller;
      for (let i = 1; i < track.tread_count; i++) {
        const x = (i / track.tread_count - .5) * track.length_m * scale;
        ctx.beginPath(); ctx.moveTo(x, y - track.width_m * scale / 2); ctx.lineTo(x, y + track.width_m * scale / 2); ctx.stroke();
      }
    }
    plate(ctx, 0, 0, model.hull.length_m * scale, model.hull.width_m * scale, model.hull.radius_m * scale, shell, colors.edge);
    for (const side of [-1, 1]) {
      plate(ctx, 0, side * model.panel.center_y_m * scale, model.panel.length_m * scale,
        model.panel.width_m * scale, model.panel.radius_m * scale, colors.panel, colors.edge);
    }
  } else if (model.kind === "radial_omni") {
    // Every complete wheel/axle assembly rotates with its radial installation angle.
    for (const mount of omniMounts(calibration)) {
      const x = mount.x_m * scale, y = -mount.y_m * scale;
      ctx.strokeStyle = colors.frame;
      ctx.lineWidth = model.suspension_width_m * scale;
      ctx.beginPath(); ctx.moveTo(x * model.suspension_inner_ratio, y * model.suspension_inner_ratio); ctx.lineTo(x, y); ctx.stroke();
      ctx.save(); ctx.translate(x, y); ctx.rotate(-mount.drive_yaw_rad);
      const l = 2 * calibration.radius_m * scale, w = model.wheel.width_m * scale;
      ctx.lineWidth = 1;
      plate(ctx, 0, 0, l, w, model.wheel.corner_radius_m * scale, colors.rubber, colors.edge);
      ctx.save(); ctx.beginPath(); ctx.rect(-l / 2, -w / 2, l, w); ctx.clip();
      // Ordinary omni-wheel rollers are transverse, without Mecanum's diagonal roller pattern.
      ctx.strokeStyle = colors.roller; ctx.lineWidth = model.wheel.roller_width_m * scale;
      for (let i = 1; i < model.wheel.roller_count; i++) {
        const offset = (i / model.wheel.roller_count - .5) * l;
        ctx.beginPath(); ctx.moveTo(offset, -w / 2); ctx.lineTo(offset, w / 2); ctx.stroke();
      }
      ctx.restore();
      plate(ctx, 0, 0, model.wheel.hub_length_m * scale, model.wheel.hub_width_m * scale,
        model.wheel.hub_radius_m * scale, colors.hub, colors.edge);
      ctx.restore();
    }
    ctx.lineWidth = 1;
    plate(ctx, 0, 0, model.hull.length_m * scale, model.hull.width_m * scale, model.hull.radius_m * scale, colors.frame, colors.edge);
    plate(ctx, 0, 0, model.deck.length_m * scale, model.deck.width_m * scale, model.deck.radius_m * scale, colors.deck, colors.edge);
    for (const side of [-1, 1]) {
      plate(ctx, side * model.armor.front_center_x_m * scale, 0, model.armor.front_length_m * scale,
        model.armor.front_width_m * scale, model.armor.radius_m * scale, shell, colors.edge);
      plate(ctx, 0, side * model.armor.side_center_y_m * scale, model.armor.side_length_m * scale,
        model.armor.side_width_m * scale, model.armor.radius_m * scale, shell, colors.edge);
    }
  } else throw new Error(`Unknown chassis visual: ${model.kind}`);
  // A fixed forward marker makes yaw readable while the world camera stays north-up.
  ctx.fillStyle = colors.mark;
  ctx.beginPath();
  for (const [i, vertex] of model.forward_marker_m.entries()) {
    const [x, y] = vertex.map(v => v * scale);
    i ? ctx.lineTo(x, -y) : ctx.moveTo(x, -y);
  }
  ctx.closePath(); ctx.fill();
}

export function drawTurret(ctx, model, scale, angle, muzzleOffset, barrelWidth) {
  ctx.save(); ctx.rotate(-angle);
  ctx.strokeStyle = model.colors.barrel; ctx.lineWidth = barrelWidth * scale;
  ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(muzzleOffset[0] * scale, -muzzleOffset[1] * scale); ctx.stroke();
  ctx.fillStyle = model.colors.turret;
  ctx.strokeStyle = model.colors.edge;
  ctx.lineWidth = 1;
  ctx.beginPath(); ctx.arc(0, 0, model.turret_radius_m * scale, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
  ctx.restore();
}
