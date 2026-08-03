# EFS File System
resource "aws_efs_file_system" "main" {
  creation_token = "${local.name_prefix}-efs"
  encrypted      = true

  tags = {
    Name = "${local.name_prefix}-efs"
  }
}

# EFS Mount Targets in Private Subnets
resource "aws_efs_mount_target" "main" {
  count           = length(aws_subnet.private)
  file_system_id  = aws_efs_file_system.main.id
  subnet_id       = aws_subnet.private[count.index].id
  security_groups = [aws_security_group.efs.id]
}

# Access Point for Hermes Agent (hermes_data)
resource "aws_efs_access_point" "hermes_data" {
  file_system_id = aws_efs_file_system.main.id

  posix_user {
    gid = 1000
    uid = 1000
  }

  root_directory {
    path = "/hermes_data"
    creation_info {
      owner_gid   = 1000
      owner_uid   = 1000
      permissions = "0755"
    }
  }

  tags = {
    Name = "${local.name_prefix}-ap-hermes-data"
  }
}

# Access Point for Scanner Sessions (seple_sessions)
resource "aws_efs_access_point" "seple_sessions" {
  file_system_id = aws_efs_file_system.main.id

  posix_user {
    gid = 1000
    uid = 1000
  }

  root_directory {
    path = "/seple_sessions"
    creation_info {
      owner_gid   = 1000
      owner_uid   = 1000
      permissions = "0755"
    }
  }

  tags = {
    Name = "${local.name_prefix}-ap-seple-sessions"
  }
}
