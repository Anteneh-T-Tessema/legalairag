from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import Duration
from aws_cdk import aws_cloudwatch as cw
from aws_cdk import aws_cloudwatch_actions as cw_actions
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sqs as sqs
from constructs import Construct


class ObservabilityStack(cdk.Stack):
    """
    CloudWatch dashboards, alarms, and SNS alerting for the IndyLeg platform.

    Monitors:
      - API: ALB 5xx rate, ECS CPU/memory, request latency
      - Ingestion: SQS DLQ depth, worker task health
      - Retrieval: Aurora connections, OpenSearch cluster health
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        env_name: str,
        api_service: ecs.FargateService,
        api_service_cluster: ecs.ICluster,
        alb_full_name: str,
        target_group_full_name: str,
        dlq: sqs.IQueue,
        ingestion_queue: sqs.IQueue,
        **kwargs: object,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        # ── SNS alert topic ──────────────────────────────────────────────────
        self.alert_topic = sns.Topic(self, "AlertTopic", topic_name=f"indyleg-alerts-{env_name}")

        # ── ALB metrics ──────────────────────────────────────────────────────
        alb_5xx = cw.Metric(
            namespace="AWS/ApplicationELB",
            metric_name="HTTPCode_ELB_5XX_Count",
            dimensions_map={"LoadBalancer": alb_full_name},
            statistic="Sum",
            period=Duration.minutes(5),
        )

        alb_latency = cw.Metric(
            namespace="AWS/ApplicationELB",
            metric_name="TargetResponseTime",
            dimensions_map={"LoadBalancer": alb_full_name},
            statistic="p99",
            period=Duration.minutes(5),
        )

        target_unhealthy = cw.Metric(
            namespace="AWS/ApplicationELB",
            metric_name="UnHealthyHostCount",
            dimensions_map={
                "LoadBalancer": alb_full_name,
                "TargetGroup": target_group_full_name,
            },
            statistic="Maximum",
            period=Duration.minutes(1),
        )

        # ── ECS metrics ─────────────────────────────────────────────────────
        ecs_dims = {
            "ClusterName": api_service_cluster.cluster_name,
            "ServiceName": api_service.service_name,
        }

        ecs_cpu = cw.Metric(
            namespace="AWS/ECS",
            metric_name="CPUUtilization",
            dimensions_map=ecs_dims,
            statistic="Average",
            period=Duration.minutes(5),
        )

        ecs_memory = cw.Metric(
            namespace="AWS/ECS",
            metric_name="MemoryUtilization",
            dimensions_map=ecs_dims,
            statistic="Average",
            period=Duration.minutes(5),
        )

        # ── SQS metrics ─────────────────────────────────────────────────────
        dlq_depth = cw.Metric(
            namespace="AWS/SQS",
            metric_name="ApproximateNumberOfMessagesVisible",
            dimensions_map={"QueueName": dlq.queue_name},
            statistic="Maximum",
            period=Duration.minutes(1),
        )

        queue_age = cw.Metric(
            namespace="AWS/SQS",
            metric_name="ApproximateAgeOfOldestMessage",
            dimensions_map={"QueueName": ingestion_queue.queue_name},
            statistic="Maximum",
            period=Duration.minutes(5),
        )

        # ── Alarms ───────────────────────────────────────────────────────────
        alb_5xx_alarm = cw.Alarm(
            self,
            "Alb5xxAlarm",
            metric=alb_5xx,
            threshold=10,
            evaluation_periods=2,
            comparison_operator=cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description="API returning elevated 5xx errors",
            treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
        )
        alb_5xx_alarm.add_alarm_action(cw_actions.SnsAction(self.alert_topic))

        latency_alarm = cw.Alarm(
            self,
            "LatencyAlarm",
            metric=alb_latency,
            threshold=5,
            evaluation_periods=3,
            comparison_operator=cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description="API p99 latency above 5 seconds",
            treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
        )
        latency_alarm.add_alarm_action(cw_actions.SnsAction(self.alert_topic))

        unhealthy_alarm = cw.Alarm(
            self,
            "UnhealthyHostAlarm",
            metric=target_unhealthy,
            threshold=1,
            evaluation_periods=2,
            comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            alarm_description="One or more ECS API tasks are unhealthy",
            treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
        )
        unhealthy_alarm.add_alarm_action(cw_actions.SnsAction(self.alert_topic))

        dlq_alarm = cw.Alarm(
            self,
            "DlqAlarm",
            metric=dlq_depth,
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            alarm_description="Messages landing in the ingestion dead-letter queue",
            treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
        )
        dlq_alarm.add_alarm_action(cw_actions.SnsAction(self.alert_topic))

        queue_age_alarm = cw.Alarm(
            self,
            "QueueAgeAlarm",
            metric=queue_age,
            threshold=3600,
            evaluation_periods=2,
            comparison_operator=cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description="Oldest ingestion message is over 1 hour old",
            treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
        )
        queue_age_alarm.add_alarm_action(cw_actions.SnsAction(self.alert_topic))

        ecs_cpu_alarm = cw.Alarm(
            self,
            "EcsCpuAlarm",
            metric=ecs_cpu,
            threshold=85,
            evaluation_periods=3,
            comparison_operator=cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description="ECS API CPU sustained above 85%",
        )
        ecs_cpu_alarm.add_alarm_action(cw_actions.SnsAction(self.alert_topic))

        # ── Dashboard ────────────────────────────────────────────────────────
        dashboard = cw.Dashboard(self, "IndyLegDashboard", dashboard_name=f"IndyLeg-{env_name}")

        dashboard.add_widgets(
            cw.TextWidget(width=24, height=1, markdown="# IndyLeg Platform — Overview"),
            # Row 1: API
            cw.GraphWidget(
                title="API 5xx Errors",
                width=8,
                left=[alb_5xx],
                left_annotations=[cw.HorizontalAnnotation(value=10, label="Alarm threshold")],
            ),
            cw.GraphWidget(
                title="API p99 Latency (s)",
                width=8,
                left=[alb_latency],
                left_annotations=[cw.HorizontalAnnotation(value=5, label="SLA limit")],
            ),
            cw.GraphWidget(
                title="Unhealthy Hosts",
                width=8,
                left=[target_unhealthy],
            ),
            # Row 2: ECS
            cw.GraphWidget(
                title="ECS CPU %",
                width=12,
                left=[ecs_cpu],
                left_annotations=[cw.HorizontalAnnotation(value=85, label="Alarm")],
            ),
            cw.GraphWidget(
                title="ECS Memory %",
                width=12,
                left=[ecs_memory],
            ),
            # Row 3: SQS
            cw.GraphWidget(
                title="DLQ Depth",
                width=8,
                left=[dlq_depth],
            ),
            cw.GraphWidget(
                title="Queue Message Age (s)",
                width=8,
                left=[queue_age],
                left_annotations=[cw.HorizontalAnnotation(value=3600, label="1 hour")],
            ),
            cw.SingleValueWidget(
                title="Active Alarms",
                width=8,
                metrics=[dlq_depth, alb_5xx],
            ),
        )
