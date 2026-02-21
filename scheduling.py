import pulumi
from pulumi import Input
from typing import Optional, Dict, TypedDict, Any
import pulumi_aws as aws

class SchedulingArgs(TypedDict, total=False):
    timezone: Input[Any]
    autoscaling_group_name: Input[Any]
    weekday_config_up: Input[Any]
    weekday_config_down: Input[Any]
    weekend_config: Input[Any]

class Scheduling(pulumi.ComponentResource):
    def __init__(self, name: str, args: SchedulingArgs, opts:Optional[pulumi.ResourceOptions] = None):
        super().__init__("components:index:Scheduling", name, args, opts)

        eks_nodes_up_morning = aws.autoscaling.Schedule(f"{name}-eks-nodes-up-morning",
            scheduled_action_name=f"{args['autoscaling_group_name']}-up",
            min_size=args["weekday_config_up"]["min"],
            max_size=args["weekday_config_up"]["max"],
            desired_capacity=args["weekday_config_up"]["desired"],
            recurrence=args["weekday_config_up"]["cron-schedule"],
            time_zone=args["timezone"],
            autoscaling_group_name=args["autoscaling_group_name"],
            opts = pulumi.ResourceOptions(parent=self))

        eks_nodes_down_evening = aws.autoscaling.Schedule(f"{name}-eks-nodes-down-evening",
            scheduled_action_name=f"{args['autoscaling_group_name']}-down",
            min_size=args["weekday_config_down"]["min"],
            max_size=args["weekday_config_down"]["max"],
            desired_capacity=args["weekday_config_down"]["desired"],
            recurrence=args["weekday_config_down"]["cron-schedule"],
            time_zone=args["timezone"],
            autoscaling_group_name=args["autoscaling_group_name"],
            opts = pulumi.ResourceOptions(parent=self))

        eks_nodes_down_weekend = aws.autoscaling.Schedule(f"{name}-eks-nodes-down-weekend",
            scheduled_action_name=f"{args['autoscaling_group_name']}-weekend",
            min_size=args["weekend_config"]["min"],
            max_size=args["weekend_config"]["max"],
            desired_capacity=args["weekend_config"]["desired"],
            recurrence=args["weekend_config"]["cron-schedule"],
            time_zone=args["timezone"],
            autoscaling_group_name=args["autoscaling_group_name"],
            opts = pulumi.ResourceOptions(parent=self))

        self.register_outputs()
