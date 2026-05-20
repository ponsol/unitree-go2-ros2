# Unitree Go2 ROS2 - Jazzy + Gazebo Harmonic Migration Guide

This document summarizes all changes made to port `unitree-go2-ros2` from
Gazebo Classic / ROS2 Humble to **ROS2 Jazzy + Gazebo Harmonic (gz-sim 8)**.

## Quick Start

```bash
# Build
cd /docker/ros2/unitree_ws
colcon build
source install/setup.bash

# Launch headless (better RTF ~1.0)
ros2 launch go2_config gazebo.launch.py gui:=false

# Walk forward
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.2, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"
```

---

## Files Changed

### 1. `robots/descriptions/go2_description/xacro/gazebo.xacro`

#### IMU Plugin
Removed legacy Gazebo Classic `<ros>` remapping block. Added `<topic>` tag
which is how gz-sim publishes sensor data.

```xml
<!-- BEFORE (broken in gz-sim) -->
<plugin filename="gz-sim-imu-system" name="gz::sim::systems::Imu">
    <ros>
        <namespace>imu</namespace>
        <remapping>~/out:=data</remapping>
    </ros>
</plugin>

<!-- AFTER -->
<sensor name="imu_sensor" type="imu">
    <topic>imu/data</topic>
    ...
    <plugin filename="gz-sim-imu-system" name="gz::sim::systems::Imu">
        <initial_orientation_as_reference>false</initial_orientation_as_reference>
    </plugin>
</sensor>
```

#### Contact Sensors
Replaced separate `<gazebo reference>` blocks (one for friction, one for sensor)
with a single merged block per lower leg link. gz-sim ignores duplicate references.
Used correct gz-sim 8 merged collision names.

```xml
<!-- MERGED into single block -->
<gazebo reference="lf_lower_leg_link">
    <mu1>0.2</mu1>
    <mu2>0.2</mu2>
    <self_collide>0</self_collide>
    <sensor name="lf_foot_contact" type="contact">
        <always_on>true</always_on>
        <update_rate>25.0</update_rate>
        <contact>
            <collision>lf_lower_leg_link_fixed_joint_lump__lf_foot_link_collision_1</collision>
        </contact>
        <plugin filename="gz-sim-contact-system" name="gz::sim::systems::Contact" />
    </sensor>
</gazebo>
```

The collision name format `${link}_fixed_joint_lump__${child}_collision_1` is how
gz-sim 8 names collisions after merging fixed joints.

#### Foot Friction
Increased foot friction for better grip:
```xml
<gazebo reference="lf_foot_link">
    <mu1>10.0</mu1>  <!-- was 0.6 -->
    <mu2>10.0</mu2>
</gazebo>
```

---

### 2. `robots/descriptions/go2_description/xacro/leg.xacro`

#### Stray Character Removed
```xml
<!-- BEFORE -->
<joint name="${name}_foot_joint" type="fixed">0

<!-- AFTER -->
<joint name="${name}_foot_joint" type="fixed">
```

#### ros2_control Hardware Plugin
```xml
<!-- BEFORE (Gazebo Classic) -->
<plugin>gazebo_ros2_control/GazeboSystem</plugin>

<!-- AFTER (gz-sim) -->
<plugin>gz_ros2_control/GazeboSimSystem</plugin>
```

#### Initial Joint Values
Added to prevent violent startup jump. Values match CHAMP standing pose
at nominal_height=0.225:
```xml
<joint name="${name}_upper_leg_joint">
    <command_interface name="effort"/>
    <state_interface name="position">
        <param name="initial_value">0.469</param>
    </state_interface>
    <state_interface name="velocity">
        <param name="initial_value">0.0</param>
    </state_interface>
</joint>
<joint name="${name}_lower_leg_joint">
    <command_interface name="effort"/>
    <state_interface name="position">
        <param name="initial_value">-0.938</param>
    </state_interface>
    <state_interface name="velocity">
        <param name="initial_value">0.0</param>
    </state_interface>
</joint>
```

---

### 3. `robots/descriptions/go2_description/config/ros_control/ros_control.yaml`

#### Joint Order Fix (Critical)
`joint_states` publishes alphabetically (`lower` before `upper`), but CHAMP
sends commands in kinematic order (`upper` before `lower`). The controller
joints list must match kinematic order so values map correctly.

```yaml
# BEFORE (wrong - caused inverted leg angles)
joints:
    - lf_hip_joint
    - lf_lower_leg_joint   # ← wrong order
    - lf_upper_leg_joint

# AFTER (correct - kinematic order)
joints:
    - lf_hip_joint
    - lf_upper_leg_joint   # ← upper first
    - lf_lower_leg_joint
```

#### PID Gains
```yaml
# Standard joints
{p: 100.0, i: 0.0, d: 1.0, i_clamp: 2.5,
 ff_velocity_scale: 0.0, antiwindup_strategy: "back_calculation"}

# Hind hip joints (higher gains reduce lateral sway)
lh_hip_joint: {p: 300.0, i: 0.0, d: 3.0, i_clamp: 1.0,
               ff_velocity_scale: 0.0, antiwindup_strategy: "back_calculation"}
rh_hip_joint: {p: 300.0, i: 0.0, d: 3.0, i_clamp: 1.0,
               ff_velocity_scale: 0.0, antiwindup_strategy: "back_calculation"}
```

Key settings:
- `ff_velocity_scale: 0.0` — velocity feedforward causes directional drift at 0.5 RTF
- `open_loop_control: false` — closed loop for better tracking
- `antiwindup_strategy: "back_calculation"` — replaces deprecated `antiwindup: true`

---

### 4. `champ/champ_base/config/ekf/footprint_to_odom.yaml`

**Critical fix** — IMU was reporting false angular velocity (z=-2.15 rad/s)
from hip sway, causing the robot to spin in circles. Removed IMU entirely
from footprint→odom EKF.

```yaml
# BEFORE (caused spinning)
odom0: odom/raw
odom0_config: [false,false,false, false,false,false, true,true,false, false,false,true, false,false,false]
imu0: imu/data
imu0_config: [false,false,false, false,false,true, false,false,false, false,false,true, false,false,false]

# AFTER (straight walking)
odom0: odom/raw
odom0_config: [false, false, false,
               false, false, false,
               true,  true,  false,   # vx, vy only
               false, false, false,
               false, false, false]
# imu0 removed entirely
```

---

### 5. `champ/champ_base/config/ekf/base_to_footprint.yaml`

Removed stale `footprint_to_odom_ekf` section that was incorrectly appended
to this file, causing config conflicts. File now only contains
`base_to_footprint_ekf` config which correctly uses IMU for roll/pitch/yaw.

---

### 6. `robots/configs/go2_config/launch/gazebo.launch.py`

#### Added imports
```python
from launch.substitutions import PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare
```

#### World SDF loading
Using `os.path.join` + `gz_args` instead of `world_sdf_file` parameter.
`world_sdf_file` with `PathJoinSubstitution` doesn't resolve correctly for
gz_sim contact plugin loading.

```python
sdf_path = os.path.join(
    get_package_share_directory("go2_config"), "worlds", "mycustom.sdf"
)
"gz_args": "-r " + sdf_path  # -r = run unpaused
```

#### CHAMP settings
```python
"publish_foot_contacts": "false",  # open loop gait (more stable)
"close_loop_odom": "true",
```

#### Spawn height
```python
declare_world_init_z = DeclareLaunchArgument("world_init_z", default_value="0.375")
```

#### IMU bridge added
```python
"/imu/data@sensor_msgs/msg/Imu[gz.msgs.IMU",
```

#### Removed invalid gz_args
```python
# REMOVED - invalid for gz_sim (valid only for gz_server)
"--plugins libgz-sim-contact-system.so"
```

---

### 7. `robots/configs/go2_config/worlds/mycustom.sdf` (NEW FILE)

Custom world replacing `default.sdf`. Key additions:
- All required world plugins explicitly declared (gz-sim ignores server.config
  when world SDF defines plugins)
- 3ms physics step for RTF ~1.0 (vs 1ms = RTF ~0.5)
- Higher ground friction

```xml
<sdf version="1.6">
  <world name="default">
    <physics name="1ms" type="ignored">
      <max_step_size>0.003</max_step_size>
      <real_time_factor>1.0</real_time_factor>
    </physics>

    <plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>
    <plugin filename="gz-sim-user-commands-system" name="gz::sim::systems::UserCommands"/>
    <plugin filename="gz-sim-scene-broadcaster-system" name="gz::sim::systems::SceneBroadcaster"/>
    <plugin filename="gz-sim-contact-system" name="gz::sim::systems::Contact"/>
    ...
  </world>
</sdf>
```

---

### 8. `~/.gz/sim/8/server.config`

Added contact system for individual foot sensor topics:
```xml
<plugin entity_name="*" entity_type="world"
        filename="gz-sim-contact-system"
        name="gz::sim::systems::Contact">
</plugin>
```

---

### 9. `champ/champ_gazebo/src/contact_sensor.cpp` (REWRITTEN)

Original code subscribed to `/world/default/contacts` which never publishes
in gz-sim 8 without explicit world-level aggregation. Rewritten to subscribe
to individual per-foot gz sensor topics instead.

Key changes:
- Subscribes to 4 individual foot sensor topics via gz transport
- Uses `create_wall_timer` (not sim timer) — fires regardless of clock state
- Resets contacts to `false` each timer tick — gz only publishes when contact
  exists, so no message = foot is airborne
- Background thread with retry for late-spawning sensors
- 100Hz timer for fast liftoff detection

```cpp
// Subscribes to:
// /world/default/model/go2/link/lf_lower_leg_link/sensor/lf_foot_contact/contact
// /world/default/model/go2/link/rf_lower_leg_link/sensor/rf_foot_contact/contact
// /world/default/model/go2/link/lh_lower_leg_link/sensor/lh_foot_contact/contact
// /world/default/model/go2/link/rh_lower_leg_link/sensor/rh_foot_contact/contact
```

---

### 10. `robots/configs/go2_config/config/gait/gait.yaml`

```yaml
nominal_height : 0.225   # Go2 standing height
swing_height : 0.02      # Low swing reduces instability
stance_duration : 0.30
com_x_translation: 0.0
knee_orientation : ">>"  # Go2 knee configuration
```

---

## Known Limitations

| Issue | Status | Notes |
|---|---|---|
| Hip sway during walking | Unfixed | CHAMP/Go2 geometry limitation |
| ~3% lateral drift | Acceptable | From hip sway forces |
| Stair climbing | Not supported | CHAMP assumes flat ground |
| RTF with GUI | ~0.5 | Run headless for RTF ~1.0 |

## Architecture

```
gz-sim sensors (gz transport)
    ↓
contact_sensor_node → /foot_contacts → state_estimation_node → /odom/raw
                                                              → /base_to_footprint_pose
imu/data ──────────────────────────────────────────────────┐
                                                           ↓
                                              base_to_footprint_ekf → /odom/local
/odom/raw ─────────────────────────────────────────────────┐
                                                           ↓
                                              footprint_to_odom_ekf → /odom

/cmd_vel → quadruped_controller_node → /joint_group_effort_controller/joint_trajectory
                                                           ↓
                                          JointTrajectoryController (effort PID)
                                                           ↓
                                              gz-sim joints (12 DOF)
```

## Root Cause Summary

| Symptom | Root Cause | Fix |
|---|---|---|
| IMU not publishing | Legacy `<ros>` block in gz-sim plugin | Removed, added `<topic>` |
| Robot dismantled visually | Duplicate `<gazebo reference>` blocks | Merged into single blocks |
| Wrong joint angles / crouched | upper/lower leg order swapped in ros_control.yaml | Fixed joint order |
| Robot spinning in circles | IMU yaw injected into footprint_to_odom EKF | Removed IMU from EKF |
| Foot contacts always false | `/world/default/contacts` not aggregating | Per-foot gz transport |
| Controller timeout at startup | Physics paused | Added `-r` to gz_args |
| Low RTF (~0.5) | 1ms physics step + GUI overhead | 3ms step, run headless |
| Robot flips at startup | Large position error at spawn | Added initial joint values |
| Rightward drift | `ff_velocity_scale: 1.0` asymmetric at low RTF | Set to 0.0 |
