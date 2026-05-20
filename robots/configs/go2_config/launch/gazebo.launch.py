import os

import launch_ros
from ament_index_python.packages import get_package_share_directory
from launch_ros.actions import Node

from launch.substitutions import PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description():

    use_sim_time = LaunchConfiguration("use_sim_time")
    robot_name = LaunchConfiguration("robot_name")

    config_pkg_share = launch_ros.substitutions.FindPackageShare(
        package="go2_config"
    ).find("go2_config")
    descr_pkg_share = launch_ros.substitutions.FindPackageShare(
        package="go2_description"
    ).find("go2_description")
    
    joints_config = os.path.join(config_pkg_share, "config/joints/joints.yaml")
    ros_control_config = os.path.join(
        config_pkg_share, "config/ros_control/ros_control.yaml"
    )
    gait_config = os.path.join(config_pkg_share, "config/gait/gait.yaml")
    links_config = os.path.join(config_pkg_share, "config/links/links.yaml")
    default_model_path = os.path.join(descr_pkg_share, "xacro/robot.xacro")

    declare_use_sim_time = DeclareLaunchArgument(
        "use_sim_time",
        default_value="true",
        description="Use simulation (Gazebo Sim) clock if true",
    )
    declare_rviz = DeclareLaunchArgument(
        "rviz", default_value="false", description="Launch rviz"
    )
    declare_robot_name = DeclareLaunchArgument(
        "robot_name", default_value="go2", description="Robot name"
    )
    declare_lite = DeclareLaunchArgument(
        "lite", default_value="false", description="Lite"
    )
    declare_ros_control_file = DeclareLaunchArgument(
        "ros_control_file",
        default_value=ros_control_config,
        description="Ros control config path",
    )
    
    # Modern Gazebo uses .sdf worlds, default to standard empty.sdf setup
    declare_gazebo_world = DeclareLaunchArgument(
        "world", default_value="default.sdf", description="Gazebo Sim SDF world name"
    )
    declare_gui = DeclareLaunchArgument(
        "gui", default_value="true", description="Use gui"
    )
    declare_world_init_x = DeclareLaunchArgument("world_init_x", default_value="0.0")
    declare_world_init_y = DeclareLaunchArgument("world_init_y", default_value="0.0")
    declare_world_init_z = DeclareLaunchArgument("world_init_z", default_value="0.375")
    declare_world_init_heading = DeclareLaunchArgument(
        "world_init_heading", default_value="0.0"
    )

    # 1. Bring up CHAMP base controllers and robot state publishers
    bringup_ld = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                get_package_share_directory("champ_bringup"),
                "launch",
                "bringup.launch.py",
            )
        ),
        launch_arguments={
            "description_path": default_model_path,
            "joints_map_path": joints_config,
            "links_map_path": links_config,
            "gait_config_path": gait_config,
            "use_sim_time": use_sim_time,
            "robot_name": robot_name,
            "gazebo": "true",
            "lite": LaunchConfiguration("lite"),
            "rviz": LaunchConfiguration("rviz"),
            "joint_controller_topic": "joint_group_effort_controller/joint_trajectory",
            "hardware_connected": "false",
            "publish_foot_contacts": "false",
            "close_loop_odom": "true",
        }.items(),
    )


    # 2. Launch the modern Gazebo Sim (Harmonic) environment
    # Maps old gui string argument into modern gz_args layout
    sdf_path = PathJoinSubstitution([
                         FindPackageShare("go2_config"), "worlds", "mycustom.sdf"
                           ])
    sdf_path = os.path.join(get_package_share_directory("go2_config"), "worlds", "mycustom.sdf")

    gazebo_sim = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                get_package_share_directory("ros_gz_sim"),
                "launch",
                "gz_sim.launch.py",
            )
        ),
        launch_arguments={
            "world_sdf_file": PathJoinSubstitution([
                         FindPackageShare("go2_config"), "worlds", "mycustom.sdf"
                           ]),
            "gz_args": "-r " + sdf_path
            #"gz_args": "-r --physics-engine gz-physics-dartsim-plugin"
            #"gz_args": "-r"
            #"gz_args": "--plugins libgz-sim-contact-system.so" 
        }.items(),
    )

    # 3. Spawn your robot model directly inside Gazebo Sim using the modern API wrapper
    spawn_robot = Node(
        package="ros_gz_sim",
        executable="create",
        output="screen",
        arguments=[
            "-world", "default",
            "-topic", "robot_description",
            "-name", robot_name,
            "-x", LaunchConfiguration("world_init_x"),
            "-y", LaunchConfiguration("world_init_y"),
            "-z", LaunchConfiguration("world_init_z"),
            "-Y", LaunchConfiguration("world_init_heading")
        ],
        parameters=[{"use_sim_time": use_sim_time}]
    )

    # 4. Bridge the contacts message topic automatically between Gazebo and ROS 2
    ros_gz_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        output="screen",
        arguments=[
            #"/world/default/contacts@champ_msgs/msg/ContactsStamped]gz.msgs.Contacts",
            "/world/empty/control@ros_gz_interfaces/srv/ControlWorld", 
            "/imu/data@sensor_msgs/msg/Imu[gz.msgs.IMU",
        ],
        parameters=[{"use_sim_time": use_sim_time}]
    )


    # 4.5 Bridge the Gazebo master clock to the ROS 2 /clock topic
    clock_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        output="screen",
        arguments=[
            "/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock"
        ]
    )


    # 5. Execute your modernized contact sensor tracking engine
    contact_sensor_node = Node(
        package="champ_gazebo",
        executable="contact_sensor",
        output="screen",
        parameters=[
            {"use_sim_time": use_sim_time},
            joints_config,
            links_config
        ]
    )

    spawn_joint_state_broadcaster = Node(
        package="controller_manager",
        executable="spawner",
        output="screen",
        arguments=["joint_state_broadcaster"],
        parameters=[
            {"use_sim_time": use_sim_time},
            {"type": "joint_state_broadcaster/JointStateBroadcaster"} 
        ]
    )

    spawn_joint_group_effort_controller = Node(
        package="controller_manager",
        executable="spawner",
        output="screen",
        arguments=[ "joint_group_effort_controller"],
        parameters=[
            {"use_sim_time": use_sim_time},
            {"type": "joint_trajectory_controller/JointTrajectoryController"} 
        ]
    )


    return LaunchDescription(
        [
            declare_use_sim_time,
            declare_rviz,
            declare_robot_name,
            declare_lite,
            declare_ros_control_file,
            declare_gazebo_world,
            declare_gui,
            declare_world_init_x,
            declare_world_init_y,
            declare_world_init_z,
            declare_world_init_heading,
            bringup_ld,
            gazebo_sim,
            spawn_robot,
            ros_gz_bridge,
            clock_bridge,
            spawn_joint_state_broadcaster,
            spawn_joint_group_effort_controller,
            contact_sensor_node,
        ]
    )
