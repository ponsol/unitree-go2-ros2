
/*
 * Copyright (C) 2012 Open Source Robotics Foundation
 * Copyright (C) 2026 - Migrated to ROS 2 Jazzy / Gazebo Sim
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
*/
#include <rclcpp/rclcpp.hpp>
#include <string>
#include <vector>
#include <functional>
#include <mutex>
#include <thread>
#include <chrono>
#include <gz/transport/Node.hh>
#include <gz/msgs/contacts.pb.h>
#include <champ_msgs/msg/contacts_stamped.hpp>

class ContactSensor : public rclcpp::Node
{
private:
    // contact_size > 0 means foot is touching ground this physics step.
    // gz publishes every physics step when contact exists, nothing when no contact.
    // We use a wall timer at 50Hz to publish and reset — if no gz message
    // arrived for a foot since last reset, that foot is not in contact.
    bool foot_contacts_[4];
    std::mutex mutex_;
    rclcpp::Publisher<champ_msgs::msg::ContactsStamped>::SharedPtr contacts_publisher_;
    gz::transport::Node gazebo_node_;
    rclcpp::TimerBase::SharedPtr timer_;

    void lfCallback(const gz::msgs::Contacts &_msg) {
        std::lock_guard<std::mutex> lock(mutex_);
        foot_contacts_[0] = (_msg.contact_size() > 0);
    }
    void rfCallback(const gz::msgs::Contacts &_msg) {
        std::lock_guard<std::mutex> lock(mutex_);
        foot_contacts_[1] = (_msg.contact_size() > 0);
    }
    void lhCallback(const gz::msgs::Contacts &_msg) {
        std::lock_guard<std::mutex> lock(mutex_);
        foot_contacts_[2] = (_msg.contact_size() > 0);
    }
    void rhCallback(const gz::msgs::Contacts &_msg) {
        std::lock_guard<std::mutex> lock(mutex_);
        foot_contacts_[3] = (_msg.contact_size() > 0);
    }

    void timerCallback()
    {
        champ_msgs::msg::ContactsStamped msg;
        msg.header.stamp = this->now();
        msg.contacts.resize(4);
        {
            std::lock_guard<std::mutex> lock(mutex_);
            for (size_t i = 0; i < 4; i++) {
                msg.contacts[i] = foot_contacts_[i];
                // Reset — gz only sends messages when contact exists.
                // If no gz message arrives before next tick, foot is airborne.
                foot_contacts_[i] = false;
            }
        }
        contacts_publisher_->publish(msg);
    }

    void subscribeWithRetry(
        const std::string &topic,
        std::function<void(const gz::msgs::Contacts &)> cb,
        const std::string &name)
    {
        int attempts = 0;
        while (rclcpp::ok() && attempts < 60) {
            if (gazebo_node_.Subscribe(topic, cb)) {
                RCLCPP_INFO(this->get_logger(), "Subscribed to %s", name.c_str());
                return;
            }
            RCLCPP_WARN(this->get_logger(), "Waiting for %s ... attempt %d/60",
                name.c_str(), ++attempts);
            std::this_thread::sleep_for(std::chrono::milliseconds(500));
        }
        RCLCPP_ERROR(this->get_logger(), "Failed to subscribe to %s", name.c_str());
    }

public:
    ContactSensor() :
        foot_contacts_{false, false, false, false},
        Node("contacts_sensor", rclcpp::NodeOptions()
            .allow_undeclared_parameters(true)
            .automatically_declare_parameters_from_overrides(true))
    {
        contacts_publisher_ = this->create_publisher<champ_msgs::msg::ContactsStamped>(
            "foot_contacts", 10);

        // Use wall timer — independent of sim clock so always fires
        timer_ = this->create_wall_timer(
            std::chrono::milliseconds(10),
            std::bind(&ContactSensor::timerCallback, this));

        std::string prefix = "/world/default/model/go2/link/";
        std::string lf = prefix + "lf_lower_leg_link/sensor/lf_foot_contact/contact";
        std::string rf = prefix + "rf_lower_leg_link/sensor/rf_foot_contact/contact";
        std::string lh = prefix + "lh_lower_leg_link/sensor/lh_foot_contact/contact";
        std::string rh = prefix + "rh_lower_leg_link/sensor/rh_foot_contact/contact";

        std::function<void(const gz::msgs::Contacts &)> lf_cb =
            [this](const gz::msgs::Contacts &m) { lfCallback(m); };
        std::function<void(const gz::msgs::Contacts &)> rf_cb =
            [this](const gz::msgs::Contacts &m) { rfCallback(m); };
        std::function<void(const gz::msgs::Contacts &)> lh_cb =
            [this](const gz::msgs::Contacts &m) { lhCallback(m); };
        std::function<void(const gz::msgs::Contacts &)> rh_cb =
            [this](const gz::msgs::Contacts &m) { rhCallback(m); };

        // Subscribe in background so constructor returns immediately
        std::thread([this, lf, rf, lh, rh, lf_cb, rf_cb, lh_cb, rh_cb]() {
            subscribeWithRetry(lf, lf_cb, "LF");
            subscribeWithRetry(rf, rf_cb, "RF");
            subscribeWithRetry(lh, lh_cb, "LH");
            subscribeWithRetry(rh, rh_cb, "RH");
            RCLCPP_INFO(this->get_logger(), "All foot contact topics subscribed.");
        }).detach();
    }
};

int main(int argc, char **argv)
{
    rclcpp::init(argc, argv);
    auto node = std::make_shared<ContactSensor>();
    rclcpp::spin(node);
    rclcpp::shutdown();
    return 0;
}
