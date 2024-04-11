# AWS Config Parametres
locals {
  AWS_REGION = "eu-central-1"
  task_execution_extra_inline_policies = [
    {
      name = "execution_logs_inline_policy"
      policy = jsonencode({
        "Version" : "2012-10-17",
        "Statement" : [
          {
            "Action" : [
              "logs:*"
            ],
            "Resource" : [
              "arn:aws:logs:*:*:*"
            ],
            "Effect" : "Allow"
          }
        ]
      })
    },
    {
      name = "execution_secrets_inline_policy"
      policy = jsonencode({
        "Version" : "2012-10-17",
        "Statement" : [
          {
            "Action" : [
              "secretsmanager:GetSecretValue"
            ],
            "Resource" : [
              "${var.api_secret_config}"
            ],
            "Effect" : "Allow"
          }
        ]
      })
    },
    {
      name = "cloudwatch"
      policy = jsonencode({
        Version = "2012-10-17"
        Statement = [
          {
            Action = [
              "cloudwatch:PutMetricData",
              "cloudwatch:DescribeAlarms",
              "cloudwatch:PutMetricAlarm",
              "cloudwatch:DeleteAlarms",
              "cloudwatch:DescribeAlarmHistory",
              "cloudwatch:DescribeAlarmsForMetric",
              "cloudwatch:GetMetricStatistics",
              "cloudwatch:ListMetrics",
              "cloudwatch:DisableAlarmActions",
              "cloudwatch:EnableAlarmActions"
            ]
            Effect   = "Allow"
            Resource = "*"
          }
        ]
        }
      )
    },
    {
      name = "autoscaling"
      policy = jsonencode(
        {
          "Version" : "2012-10-17",
          "Statement" : [
            {
              "Action" : [
                "application-autoscaling:*"
              ],
              "Resource" : [
                "*"
              ],
              "Effect" : "Allow"
            }
          ]
        }
      )
    }
  ]
  task_extra_inline_policies = [
    {
      name = "ecr_inline_policy"
      policy = jsonencode({
        Version = "2012-10-17"
        Statement = [
          {
            Action = [
              "ecr:GetAuthorizationToken",
              "ecr:DescribeImageScanFindings",
              "ecr:GetLifecyclePolicyPreview",
              "ecr:GetDownloadUrlForLayer",
              "ecr:DescribeImageReplicationStatus",
              "ecr:ListTagsForResource",
              "ecr:ListImages",
              "ecr:BatchGetRepositoryScanningConfiguration",
              "ecr:BatchGetImage",
              "ecr:DescribeImages",
              "ecr:DescribeRepositories",
              "ecr:BatchCheckLayerAvailability",
              "ecr:GetRepositoryPolicy",
              "ecr:GetLifecyclePolicy"
            ]
            Effect = "Allow"
            Resource = [
              "arn:aws:ecr:${local.AWS_REGION}:${data.aws_caller_identity.current.account_id}:repository/*"
            ]
          },
        ]
      })
    },
    {
      name = "ecs_inline_policy"
      policy = jsonencode({
        "Version" : "2012-10-17",
        "Statement" : [
          {
            "Action" : [
              "ecs:DescribeServices",
              "ecs:UpdateService",
              "ecs:List*"
            ],
            "Resource" : [
              "*"
            ],
            "Effect" : "Allow"
          }
        ]
      })
    },
    {
      name = "logs_inline_policy"
      policy = jsonencode({
        "Version" : "2012-10-17",
        "Statement" : [
          {
            "Action" : [
              "logs:*"
            ],
            "Resource" : [
              "arn:aws:logs:*:*:*"
            ],
            "Effect" : "Allow"
          }
        ]
      })
    },
    {
      name = "cloudwatch"
      policy = jsonencode({
        Version = "2012-10-17"
        Statement = [
          {
            Action = [
              "cloudwatch:PutMetricData",
              "cloudwatch:DescribeAlarms",
              "cloudwatch:PutMetricAlarm",
              "cloudwatch:DeleteAlarms",
              "cloudwatch:DescribeAlarmHistory",
              "cloudwatch:DescribeAlarmsForMetric",
              "cloudwatch:GetMetricStatistics",
              "cloudwatch:ListMetrics",
              "cloudwatch:DisableAlarmActions",
              "cloudwatch:EnableAlarmActions"
            ]
            Effect   = "Allow"
            Resource = "*"
          }
        ]
        }
      )
    },
    {
      name = "autoscaling"
      policy = jsonencode(
        {
          "Version" : "2012-10-17",
          "Statement" : [
            {
              "Action" : [
                "application-autoscaling:*"
              ],
              "Resource" : [
                "*"
              ],
              "Effect" : "Allow"
            }
          ]
        }
      )
    }
  ]
  container_definitions = [
    {
      "name" : "${local.project_name}-task-container",
      "image" : "${var.ecs_task_container_definitions_image}:${var.image_tag}",
      "cpu" : "${var.ecs_task_container_definitions_cpu}",
      "memory" : "${var.ecs_task_container_definitions_memory}",
      "networkMode" : "awsvpc",
      "logConfiguration" : {
        "logDriver" : "awslogs",
        "options" : {
          "awslogs-group" : "/ecs/p2p_schedule_api_of_carriers_service",
          "awslogs-region" : "${local.AWS_REGION}",
          "awslogs-stream-prefix" : "ecs"
        }
      },
      "portMappings" : [
        {
          "containerPort" : 8000,
          "hostPort" : 8000
        }
      ],
      environment = [for k, v in var.static_variables : { name : k, value : v }],
      secrets : [
        {
          "name" : "MONGO_URL",
          "valueFrom" : "${var.api_secret_config}:MONGO_URL::"
        },
        {
          "name" : "CMA_URL",
          "valueFrom" : "${var.api_secret_config}:CMA_URL::"
        },
        {
          "name" : "CMA_TOKEN",
          "valueFrom" : "${var.api_secret_config}:CMA_TOKEN::"
        },
        {
          "name" : "SUDU_URL",
          "valueFrom" : "${var.api_secret_config}:SUDU_URL::"
        },
        {
          "name" : "SUDU_TOKEN",
          "valueFrom" : "${var.api_secret_config}:SUDU_TOKEN::"
        },
        {
          "name" : "HMM_URL",
          "valueFrom" : "${var.api_secret_config}:HMM_URL::"
        },
        {
          "name" : "HMM_TOKEN",
          "valueFrom" : "${var.api_secret_config}:HMM_TOKEN::"
        },
        {
          "name" : "IQAX_URL",
          "valueFrom" : "${var.api_secret_config}:IQAX_URL::"
        },
        {
          "name" : "IQAX_TOKEN",
          "valueFrom" : "${var.api_secret_config}:IQAX_TOKEN::"
        },
        {
          "name" : "MAEU_P2P",
          "valueFrom" : "${var.api_secret_config}:MAEU_P2P::"
        },
        {
          "name" : "MAEU_LOCATION",
          "valueFrom" : "${var.api_secret_config}:MAEU_LOCATION::"
        },
        {
          "name" : "MAEU_CUTOFF",
          "valueFrom" : "${var.api_secret_config}:MAEU_CUTOFF::"
        },
        {
          "name" : "MAEU_TOKEN",
          "valueFrom" : "${var.api_secret_config}:MAEU_TOKEN::"
        },
        {
          "name" : "MAEU_TOKEN2",
          "valueFrom" : "${var.api_secret_config}:MAEU_TOKEN2::"
        },
        {
          "name" : "ONEY_URL",
          "valueFrom" : "${var.api_secret_config}:ONEY_URL::"
        },
        {
          "name" : "ONEY_TURL",
          "valueFrom" : "${var.api_secret_config}:ONEY_TURL::"
        },
        {
          "name" : "ONEY_TOKEN",
          "valueFrom" : "${var.api_secret_config}:ONEY_TOKEN::"
        },
        {
          "name" : "ONEY_AUTH",
          "valueFrom" : "${var.api_secret_config}:ONEY_AUTH::"
        },
        {
          "name" : "ZIM_URL",
          "valueFrom" : "${var.api_secret_config}:ZIM_URL::"
        },
        {
          "name" : "ZIM_TURL",
          "valueFrom" : "${var.api_secret_config}:ZIM_TURL::"
        },
        {
          "name" : "ZIM_TOKEN",
          "valueFrom" : "${var.api_secret_config}:ZIM_TOKEN::"
        },
        {
          "name" : "ZIM_CLIENT",
          "valueFrom" : "${var.api_secret_config}:ZIM_CLIENT::"
        },
        {
          "name" : "ZIM_SECRET",
          "valueFrom" : "${var.api_secret_config}:ZIM_SECRET::"
        },
        {
          "name" : "MSCU_URL",
          "valueFrom" : "${var.api_secret_config}:MSCU_URL::"
        },
        {
          "name" : "MSCU_AUD",
          "valueFrom" : "${var.api_secret_config}:MSCU_AUD::"
        },
        {
          "name" : "MSCU_OAUTH",
          "valueFrom" : "${var.api_secret_config}:MSCU_OAUTH::"
        },
        {
          "name" : "MSCU_CLIENT",
          "valueFrom" : "${var.api_secret_config}:MSCU_CLIENT::"
        },
        {
          "name" : "MSCU_THUMBPRINT",
          "valueFrom" : "${var.api_secret_config}:MSCU_THUMBPRINT::"
        },
        {
          "name" : "MSCU_SCOPE",
          "valueFrom" : "${var.api_secret_config}:MSCU_SCOPE::"
        },
        {
          "name" : "MSCU_RSA_KEY",
          "valueFrom" : "${var.api_secret_config}:MSCU_RSA_KEY::"
        },
        {
          "name" : "HLCU_TOKEN_URL",
          "valueFrom" : "${var.api_secret_config}:HLCU_TOKEN_URL::"
        },
        {
          "name" : "HLCU_URL",
          "valueFrom" : "${var.api_secret_config}:HLCU_URL::"
        },
        {
          "name" : "HLCU_CLIENT_ID",
          "valueFrom" : "${var.api_secret_config}:HLCU_CLIENT_ID::"
        },
        {
          "name" : "HLCU_CLIENT_SECRET",
          "valueFrom" : "${var.api_secret_config}:HLCU_CLIENT_SECRET::"
        },
        {
          "name" : "HLCU_USER_ID",
          "valueFrom" : "${var.api_secret_config}:HLCU_USER_ID::"
        },
        {
          "name" : "HLCU_PASSWORD",
          "valueFrom" : "${var.api_secret_config}:HLCU_PASSWORD::"
        },
        {
          "name" : "BASIC_USER",
          "valueFrom" : "${var.api_secret_config}:BASIC_USER::"
        },
        {
          "name" : "BASIC_PW",
          "valueFrom" : "${var.api_secret_config}:BASIC_PW::"
        },
        {
          "name" : "REDIS_HOST",
          "valueFrom" : "${var.api_secret_config}:REDIS_HOST::"
        },
        {
          "name" : "REDIS_PORT",
          "valueFrom" : "${var.api_secret_config}:REDIS_PORT::"
        },
        {
          "name" : "REDIS_DB",
          "valueFrom" : "${var.api_secret_config}:REDIS_DB::"
        },
        {
          "name" : "REDIS_USER",
          "valueFrom" : "${var.api_secret_config}:REDIS_USER::"
        },
        {
          "name" : "REDIS_PW",
          "valueFrom" : "${var.api_secret_config}:REDIS_PW::"
        }
      ]
    }
  ]
  project_name       = "p2p-schedule-api-of-carriers"
  project_name_abreb = "p2papicarriers"
}