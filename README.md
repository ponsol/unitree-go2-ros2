# Unitree Go2 ROS2

![Unitree Go2](https://camo.githubusercontent.com/45aa012c22000a6e5c31fa954cd32c228ee22d95dfa0289a2899a8355eadb2f8/68747470733a2f2f6f73732d676c6f62616c2d63646e2e756e69747265652e636f6d2f7374617469632f63343837663933653036393534313030613434666163343434326239346439345f323838783233382e706e67)

Unitree Go2 robot configured with the [CHAMP](https://github.com/chvmp/champ) quadruped controller framework. This branch targets **ROS2 Jazzy + Gazebo Harmonic (gz-sim 8)**.

> **Branch:** `jazzy` — For ROS2 Humble + Gazebo Classic, see the [`humble`](../../tree/humble) branch.

---

## Demo

### Gazebo Simulation

[![Gazebo Demo](https://raw.githubusercontent.com/ponsol/unitree-go2-ros2/jazzy-sjk/assets/bot-gz-thumb.png)](https://raw.githubusercontent.com/ponsol/unitree-go2-ros2/jazzy-sjk/assets/bot-gz.mp4)

### RViz Visualization

[![RViz Demo](https://raw.githubusercontent.com/ponsol/unitree-go2-ros2/jazzy-sjk/assets/bot-rviz-thumb.png)](https://raw.githubusercontent.com/ponsol/unitree-go2-ros2/jazzy-sjk/assets/bot-rviz.mp4)

---

## Overview

This package provides:
- Full Gazebo Harmonic simulation of the Unitree Go2
- CHAMP-based trot gait locomotion controller
- IMU, contact sensor, and odometry integration
- EKF-based state estimation
- Teleoperation via `cmd_vel`

---

## Requirements

| Component | Version |
|---|---|
| ROS2 | Jazzy Jalisco |
| Gazebo | Harmonic (gz-sim 8) |
| Ubuntu | 24.04 |
| ros2_control | Jazzy |
| robot_localization | Jazzy |

---

## Installation

### 1. Install ROS2 Jazzy

Follow the [official ROS2 Jazzy installation guide](https://docs.ros.org/en/jazzy/Installation.html).

### 2. Install Dependencies

```bash
sudo apt update
sudo apt install -y \
  ros-jazzy-ros-gz \
  ros-jazzy-gz-ros2-control \
  ros-jazzy-ros2-control \
  ros-jazzy-ros2-controllers \
  ros-jazzy-robot-localization \
  ros-jazzy-xacro \
  ros-jazzy-joint-state-publisher \
  ros-jazzy-teleop-twist-keyboard
```

### 3. Clone Repository

```bash
mkdir -p ~/ros2_ws/src
cd ~/ros2_ws/src
git clone --recurse-submodules -b jazzy \
  https://github.com/ponsol/unitree-go2-ros2.git
```

### 4. Build

```bash
cd ~/ros2_ws
colcon build --symlink-install
source install/setup.bash
```

### 5. Server Config

Add the contact system plugin to Gazebo's server config so foot sensors work:

```bash
mkdir -p ~/.gz/sim/8
cat > ~/.gz/sim/8/server.config << 'CONF'
<server_config>
  <plugins>
    <plugin entity_name="*" entity_type="world"
            filename="gz-sim-physics-system"
            name="gz::sim::systems::Physics"/>
    <plugin entity_name="*" entity_type="world"
            filename="gz-sim-user-commands-system"
            name="gz::sim::systems::UserCommands"/>
    <plugin entity_name="*" entity_type="world"
            filename="gz-sim-scene-broadcaster-system"
            name="gz::sim::systems::SceneBroadcaster"/>
    <plugin entity_name="*" entity_type="world"
            filename="gz-sim-contact-system"
            name="gz::sim::systems::Contact"/>
  </plugins>
</server_config>
CONF
```

---

## Usage

### Launch Simulation (Headless — better performance)

```bash
source install/setup.bash
ros2 launch go2_config gazebo.launch.py gui:=false
```

### Launch Simulation (With GUI)

```bash
ros2 launch go2_config gazebo.launch.py
```

> **Tip:** For better real-time performance (RTF ~1.0), run headless and connect
> the GUI separately:
> ```bash
> gz sim -g
> ```

### Teleoperation

```bash
# Walk forward
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.2, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"

# Stop
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"

# Keyboard teleop
ros2 run teleop_twist_keyboard teleop_twist_keyboard
```

### Launch with Velodyne LiDAR

```bash
ros2 launch go2_config gazebo_velodyne.launch.py gui:=false
```

---

## Gait Configuration

Edit `robots/configs/go2_config/config/gait/gait.yaml`:

```yaml
gait:
  knee_orientation : ">>"
  nominal_height : 0.225       # Body height above ground (m)
  swing_height : 0.02          # Foot lift height during swing (m)
  stance_duration : 0.30       # Duration of stance phase (s)
  max_linear_velocity_x : 0.3  # Max forward speed (m/s)
  max_linear_velocity_y : 0.25 # Max lateral speed (m/s)
  max_angular_velocity_z : 0.5 # Max turning speed (rad/s)
```

---

## Package Structure

```
unitree-go2-ros2/
├── champ/                          # CHAMP controller framework
│   ├── champ_base/                 # State estimation + quadruped controller
│   ├── champ_bringup/              # Launch files
│   ├── champ_gazebo/               # Gazebo contact sensor node
│   └── champ_msgs/                 # Custom message types
└── robots/
    ├── descriptions/
    │   └── go2_description/        # URDF, meshes, ros2_control config
    │       ├── xacro/
    │       │   ├── robot.xacro     # Main robot description
    │       │   ├── gazebo.xacro    # Gazebo plugins + sensors
    │       │   └── leg.xacro       # Leg kinematics + ros2_control
    │       └── config/
    │           └── ros_control/    # PID gains, controller config
    └── configs/
        └── go2_config/             # Robot-specific config
            ├── config/
            │   ├── gait/           # Gait parameters
            │   ├── joints/         # Joint mapping
            │   └── links/          # Link mapping
            ├── launch/
            │   └── gazebo.launch.py
            └── worlds/
                └── mycustom.sdf    # Custom Gazebo world
```

---

## Architecture

```
/cmd_vel ──→ quadruped_controller_node (CHAMP)
                        │
                        ▼
         joint_group_effort_controller
         (JointTrajectoryController + PID)
                        │
                        ▼
              gz-sim 12-DOF joints
                        │
              ┌─────────┴──────────┐
              │                    │
         foot contacts           IMU
              │                    │
    contact_sensor_node    base_to_footprint_ekf
              │                    │
         /foot_contacts      /odom/local
              │
    state_estimation_node
              │
          /odom/raw
              │
    footprint_to_odom_ekf
              │
           /odom
```

---

## Known Limitations

- **Hip sway** — Minor lateral body sway during trot gait. This is a
  fundamental limitation of the CHAMP controller with the Go2 geometry.
  Does not affect straight-line navigation significantly (<3% lateral drift).
- **Stair climbing** — Not supported. CHAMP assumes flat ground.
- **GUI performance** — Running with GUI reduces RTF to ~0.5.
  Use `gui:=false` for best performance.

---

## Jazzy Migration Notes

This branch contains significant changes from the original `humble` branch to
support ROS2 Jazzy + Gazebo Harmonic. See
[JAZZY_HARMONIC_MIGRATION.md](JAZZY_HARMONIC_MIGRATION.md) for the full
list of changes.

Key fixes include:
- Gazebo Classic → gz-sim plugin migration
- Joint order fix (upper/lower leg swap)
- Contact sensor rewrite for gz-sim 8
- EKF IMU yaw removal (was causing rotation)
- Custom world SDF with 3ms physics step

---

## Acknowledgements

- [Unitree Robotics](https://www.unitree.com) — Go2 robot description (URDF)
- [CHAMP](https://github.com/chvmp/champ) — Quadruped controller framework
- [anujjain-dev/unitree-go2-ros2](https://github.com/anujjain-dev/unitree-go2-ros2) — Original repository
