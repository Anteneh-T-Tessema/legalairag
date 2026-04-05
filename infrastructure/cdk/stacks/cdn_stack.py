from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import Duration
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3deploy
from constructs import Construct


class CdnStack(cdk.Stack):
    """
    CloudFront distribution for the IndyLeg platform.

    Origins:
      /api/*   → ALB (API)
      /*       → S3  (UI static assets, default)
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        env_name: str,
        alb: elbv2.IApplicationLoadBalancer,
        **kwargs: object,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        # ── S3 bucket for UI assets ──────────────────────────────────────────
        self.ui_bucket = s3.Bucket(
            self,
            "UiBucket",
            bucket_name=f"indyleg-ui-{env_name}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=cdk.RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # ── CloudFront distribution ──────────────────────────────────────────
        oac_s3_origin = origins.S3BucketOrigin.with_origin_access_control(self.ui_bucket)

        api_origin = origins.HttpOrigin(
            alb.load_balancer_dns_name,
            protocol_policy=cloudfront.OriginProtocolPolicy.HTTP_ONLY,
        )

        self.distribution = cloudfront.Distribution(
            self,
            "Distribution",
            comment=f"IndyLeg CDN ({env_name})",
            default_behavior=cloudfront.BehaviorOptions(
                origin=oac_s3_origin,
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
            ),
            additional_behaviors={
                "/api/*": cloudfront.BehaviorOptions(
                    origin=api_origin,
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                    cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                    origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER,
                ),
                "/health": cloudfront.BehaviorOptions(
                    origin=api_origin,
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                ),
            },
            default_root_object="index.html",
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_page_path="/index.html",
                    response_http_status=200,
                    ttl=Duration.seconds(0),
                ),
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_page_path="/index.html",
                    response_http_status=200,
                    ttl=Duration.seconds(0),
                ),
            ],
        )

        # ── Deploy UI build output to S3 ─────────────────────────────────────
        s3deploy.BucketDeployment(
            self,
            "DeployUi",
            sources=[s3deploy.Source.asset("../../ui/dist")],
            destination_bucket=self.ui_bucket,
            distribution=self.distribution,
            distribution_paths=["/*"],
        )

        # ── Outputs ──────────────────────────────────────────────────────────
        cdk.CfnOutput(
            self,
            "DistributionUrl",
            value=f"https://{self.distribution.distribution_domain_name}",
            description="CloudFront URL for the IndyLeg platform",
        )

        cdk.CfnOutput(
            self,
            "UiBucketName",
            value=self.ui_bucket.bucket_name,
            description="S3 bucket for UI static assets",
        )
