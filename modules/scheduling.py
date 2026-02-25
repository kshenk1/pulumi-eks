import pulumi
from pulumi import Input
from typing import Optional, Dict, TypedDict, Any
import pulumi_aws as aws

class SchedulingArgs(TypedDict):
    timezone: Input[str]
    autoscaling_group_name: Input[str]
    weekday_config_up: Input[dict]
    weekday_config_down: Input[dict]
    weekend_config: Input[dict]

class Scheduling(pulumi.ComponentResource):
    def __init__(self, provider: aws.Provider, name: str, args: SchedulingArgs, opts:Optional[pulumi.ResourceOptions] = None):
        super().__init__("components:index:Scheduling", name, args, opts)

        eks_nodes_up_morning = aws.autoscaling.Schedule(f"{name}-eks-nodes-up-morning",
            scheduled_action_name=args["autoscaling_group_name"].apply(lambda n: f"{n}-up"),
            min_size=args["weekday_config_up"]["min"],
            max_size=args["weekday_config_up"]["max"],
            desired_capacity=args["weekday_config_up"]["desired"],
            recurrence=args["weekday_config_up"]["cron_schedule"],
            time_zone=args["timezone"],
            autoscaling_group_name=args["autoscaling_group_name"],
            opts = pulumi.ResourceOptions(parent=self, provider=provider))

        eks_nodes_down_evening = aws.autoscaling.Schedule(f"{name}-eks-nodes-down-evening",
            scheduled_action_name=args["autoscaling_group_name"].apply(lambda n: f"{n}-down"),
            min_size=args["weekday_config_down"]["min"],
            max_size=args["weekday_config_down"]["max"],
            desired_capacity=args["weekday_config_down"]["desired"],
            recurrence=args["weekday_config_down"]["cron_schedule"],
            time_zone=args["timezone"],
            autoscaling_group_name=args["autoscaling_group_name"],
            opts = pulumi.ResourceOptions(parent=self, provider=provider))

        eks_nodes_down_weekend = aws.autoscaling.Schedule(f"{name}-eks-nodes-down-weekend",
            scheduled_action_name=args["autoscaling_group_name"].apply(lambda n: f"{n}-weekend"),
            min_size=args["weekend_config"]["min"],
            max_size=args["weekend_config"]["max"],
            desired_capacity=args["weekend_config"]["desired"],
            recurrence=args["weekend_config"]["cron_schedule"],
            time_zone=args["timezone"],
            autoscaling_group_name=args["autoscaling_group_name"],
            opts = pulumi.ResourceOptions(parent=self, provider=provider))

        self.register_outputs({
            "eks_nodes_up_morning": eks_nodes_up_morning.id,
            "eks_nodes_down_evening": eks_nodes_down_evening.id,
            "eks_nodes_down_weekend": eks_nodes_down_weekend.id,
        })
