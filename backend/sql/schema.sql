-- ============================================================
--  UI 自动化平台 · schema.sql
--  MySQL 8.0+ / utf8mb4
--  事实来源：本文件（M1 开工后由文档附录升级为唯一 DDL 源）
--  含 M2 修正：element.deleted_seq（软删唯一键）、element_locator.probe_detail
--  注意：端只有 WEB / ANDROID / IOS（D5，无 WAP）
-- ============================================================
SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ── 1. project —— 显式路由（P1）────────────────────────────
CREATE TABLE IF NOT EXISTS `project` (
  `id`                BIGINT       NOT NULL AUTO_INCREMENT,
  `name`              VARCHAR(128) NOT NULL COMMENT '项目名称',
  `code`              VARCHAR(64)  NOT NULL COMMENT '项目英文标识，唯一',
  -- ★ 显式路由三件套：禁止用"用例里用了什么动作"反推端类型
  `platform`          ENUM('WEB','ANDROID','IOS') NOT NULL COMMENT '目标端（业务维度）',
  `engine_key`        VARCHAR(64)  NOT NULL COMMENT '引擎适配器 key（技术维度）',
  `target_id`         BIGINT       NULL     COMMENT '默认执行目标',
  `description`       VARCHAR(512) NULL,
  `default_timeout_ms` INT         NOT NULL DEFAULT 15000,
  `is_deleted`        TINYINT(1)   NOT NULL DEFAULT 0,
  `deleted_at`        DATETIME     NULL,
  `created_at`        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_project_code` (`code`),
  KEY `idx_project_platform_engine` (`platform`, `engine_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='测试项目';

-- ── 2. execution_target —— 执行目标（环境/设备）──────────────
CREATE TABLE IF NOT EXISTS `execution_target` (
  `id`          BIGINT       NOT NULL AUTO_INCREMENT,
  `project_id`  BIGINT       NOT NULL,
  `name`        VARCHAR(128) NOT NULL,
  `platform`    ENUM('WEB','ANDROID','IOS') NOT NULL,
  `engine_key`  VARCHAR(64)  NOT NULL,
  `base_url`    VARCHAR(512) NULL COMMENT 'Web 基址；移动端可为空',
  `options`     JSON         NOT NULL COMMENT '设备描述符 / 浏览器参数',
  `enabled`     TINYINT(1)   NOT NULL DEFAULT 1,
  -- ★ M3.6 GAP-42：软删三列（D29/D30/D31），与 element / test_suite 同款
  `is_deleted`  TINYINT(1)   NOT NULL DEFAULT 0,
  `deleted_at`  DATETIME     NULL,
  `deleted_seq` BIGINT       NOT NULL DEFAULT 0 COMMENT '软删序号：0=未删；删除时置为自身 id',
  `created_at`  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  -- 项目内活记录 name 唯一；软删行 deleted_seq=id 互不冲突（D30）
  UNIQUE KEY `uk_target_name` (`project_id`, `name`, `deleted_seq`),
  KEY `idx_target_project` (`project_id`, `is_deleted`)
  `created_at` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_target_platform_engine` (`platform`, `engine_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='执行目标（环境/设备）';

-- ── 3. element —— 逻辑元素（树形；不含任何定位信息）──────────
CREATE TABLE IF NOT EXISTS `element` (
  `id`           BIGINT       NOT NULL AUTO_INCREMENT,
  `project_id`   BIGINT       NOT NULL,
  `parent_id`    BIGINT       NOT NULL DEFAULT 0 COMMENT '父节点，0=根',
  `path`         VARCHAR(512) NOT NULL DEFAULT '/' COMMENT '物化路径，含自身，如 /7/12/45/',
  `element_name` VARCHAR(255) NOT NULL COMMENT '逻辑名，如「登录按钮」',
  `node_type`    ENUM('ELEMENT','FOLDER') NOT NULL DEFAULT 'ELEMENT',
  `description`  VARCHAR(512) NULL,
  `memo`         TEXT         NULL COMMENT '业务语义说明，供人与 AI 理解',
  `is_shared`    TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '1=项目内共享（M2 固定为 1，二期启用跨项目）',
  `sort`         INT          NOT NULL DEFAULT 0,
  `is_deleted`   TINYINT(1)   NOT NULL DEFAULT 0,
  -- ★ M2：软删序号（0=未删；删除时置为自身 id），使已删记录不撞唯一键
  `deleted_seq`  BIGINT       NOT NULL DEFAULT 0 COMMENT '软删序号：0=未删；删除时置为自身 id',
  `deleted_at`   DATETIME     NULL,
  `created_by`   BIGINT       NULL,
  `updated_by`   BIGINT       NULL,
  `created_at`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_element_name` (`project_id`, `parent_id`, `element_name`, `deleted_seq`),
  KEY `idx_element_project` (`project_id`, `is_deleted`),
  KEY `idx_element_path` (`project_id`, `path`),
  KEY `idx_element_name` (`project_id`, `element_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='逻辑元素（树形）';

-- ── 4. ★ element_locator —— 多端定位符映射（P2）──────────────
CREATE TABLE IF NOT EXISTS `element_locator` (
  `id`            BIGINT       NOT NULL AUTO_INCREMENT,
  `element_id`    BIGINT       NOT NULL,
  -- ★ 二维定位：platform（业务端） × engine_key（技术引擎）
  `platform`      ENUM('WEB','ANDROID','IOS') NOT NULL,
  `engine_key`    VARCHAR(64)  NOT NULL DEFAULT '*' COMMENT '* = 该平台下所有引擎通用',
  -- ★ 只存语义类型，引擎语汇由适配器翻译（FR18）
  `locator_type`  VARCHAR(32)  NOT NULL COMMENT '语义定位类型，受 platform + engine 约束',
  `locator_value` TEXT         NOT NULL COMMENT '语义层表达式，不含引擎前缀',
  `priority`      INT          NOT NULL DEFAULT 100 COMMENT '组内回退顺序，小的先试',
  `is_primary`    TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '首选标记（仅展示，不影响执行顺序）',
  `verified_at`   DATETIME     NULL,
  `status`        ENUM('UNVERIFIED','VALID','INVALID') NOT NULL DEFAULT 'UNVERIFIED',
  `probe_detail`  JSON         NULL COMMENT '最近验证：{matched, verdict, sample, error, at}',
  `enabled`       TINYINT(1)   NOT NULL DEFAULT 1,
  `remark`        VARCHAR(255) NULL,
  `created_at`    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_locator` (`element_id`, `platform`, `engine_key`, `locator_type`, `locator_value`(128)),
  KEY `idx_locator_lookup` (`element_id`, `platform`, `engine_key`, `enabled`, `priority`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='元素多端定位符映射';

-- ── 5. action_catalog —— 统一动作字典（P3）─────────────────
CREATE TABLE IF NOT EXISTS `action_catalog` (
  `id`               BIGINT      NOT NULL AUTO_INCREMENT,
  `action_key`       VARCHAR(64) NOT NULL COMMENT '统一动作标识（英文 snake_case，D6）',
  `name`             VARCHAR(64) NOT NULL COMMENT '中文名（仅展示）',
  `category`         ENUM('ELEMENT','APP_LIFECYCLE','CONTEXT','NAVIGATION','ASSERT','DATA','SYSTEM','NETWORK') NOT NULL,
  `platforms`        JSON        NOT NULL,
  `engines`          JSON        NOT NULL COMMENT '[] = 平台内建动作',
  `params_schema`    JSON        NOT NULL,
  `requires_element` TINYINT(1)  NOT NULL DEFAULT 0,
  `sort`             INT         NOT NULL DEFAULT 0,
  `enabled`          TINYINT(1)  NOT NULL DEFAULT 1,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_action_key` (`action_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='统一动作字典';

-- ── 6. test_case ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `test_case` (
  `id`          BIGINT       NOT NULL AUTO_INCREMENT,
  `project_id`  BIGINT       NOT NULL,
  `title`       VARCHAR(255) NOT NULL,
  `description` VARCHAR(1024) NULL,
  `state`       TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '1=启用 0=停用',
  `is_deleted`  TINYINT(1)   NOT NULL DEFAULT 0,
  `deleted_at`  DATETIME     NULL,
  `created_by`  BIGINT       NULL,
  `updated_by`  BIGINT       NULL,
  `created_at`  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_case_project` (`project_id`, `is_deleted`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='测试用例';
-- 注：无 project_type —— 端类型统一从 project 继承（P1）

-- ── 7. test_step ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `test_step` (
  `id`          BIGINT       NOT NULL AUTO_INCREMENT,
  `case_id`     BIGINT       NOT NULL,
  `seq`         INT          NOT NULL COMMENT '执行顺序，从 1 开始',
  `action_key`  VARCHAR(64)  NOT NULL COMMENT '指向 action_catalog.action_key',
  `element_id`  BIGINT       NULL COMMENT 'requires_element=1 时必填',
  `params`      JSON         NOT NULL COMMENT '动作参数，schema 见 action_catalog.params_schema',
  `output_var`  VARCHAR(64)  NULL,
  `assert_expr` JSON         NULL,
  `timeout_ms`  INT          NULL,
  `on_failure`  ENUM('ABORT','CONTINUE','RETRY') NOT NULL DEFAULT 'ABORT',
  `retry_times` INT          NOT NULL DEFAULT 0,
  `enabled`     TINYINT(1)   NOT NULL DEFAULT 1,
  `remark`      VARCHAR(255) NULL,
  `created_at`  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_step_seq` (`case_id`, `seq`),
  KEY `idx_step_element` (`element_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用例步骤';

-- ── 8. test_suite / 8.1 test_suite_case —— 用例集 ───────────
CREATE TABLE IF NOT EXISTS `test_suite` (
  `id`               BIGINT       NOT NULL AUTO_INCREMENT,
  `project_id`       BIGINT       NOT NULL,
  `name`             VARCHAR(128) NOT NULL,
  `description`      VARCHAR(512) NULL,
  `schedule_cron`    VARCHAR(64)  NULL COMMENT '5 段 cron（分 时 日 月 周）；空=只手动',
  `schedule_enabled` TINYINT(1)   NOT NULL DEFAULT 0,
  `last_run_at`      DATETIME     NULL,
  `is_deleted`       TINYINT(1)   NOT NULL DEFAULT 0,
  `deleted_seq`      BIGINT       NOT NULL DEFAULT 0 COMMENT '软删序号：0=未删；删除时置为自身 id',
  `deleted_at`       DATETIME     NULL,
  `created_by`       BIGINT       NULL,
  `created_at`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_suite_name` (`project_id`, `name`, `deleted_seq`),
  KEY `idx_suite_project` (`project_id`, `is_deleted`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用例集（执行单元）';

CREATE TABLE IF NOT EXISTS `test_suite_case` (
  `id`         BIGINT     NOT NULL AUTO_INCREMENT,
  `suite_id`   BIGINT     NOT NULL,
  `case_id`    BIGINT     NOT NULL,
  `sort`       INT        NOT NULL DEFAULT 0,
  `enabled`    TINYINT(1) NOT NULL DEFAULT 1,
  `created_at` DATETIME   NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_suite_case` (`suite_id`, `case_id`),
  KEY `idx_suite_case_case` (`case_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用例集成员';

-- ── 9. execution ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `execution` (
  `id`           BIGINT      NOT NULL AUTO_INCREMENT,
  `project_id`   BIGINT      NOT NULL,
  `target_id`    BIGINT      NULL COMMENT '执行目标快照来源',
  -- M3.3：由用例集触发时记录来源（name 为快照，改名不影响历史）
  `suite_id`     BIGINT      NULL,
  `suite_name`   VARCHAR(128) NULL,
  `trigger_type` ENUM('MANUAL','SCHEDULE','API') NOT NULL DEFAULT 'MANUAL',
  `case_ids`     JSON        NOT NULL,
  `engine_key`   VARCHAR(64) NOT NULL COMMENT '执行时实际引擎（快照）',
  `platform`     ENUM('WEB','ANDROID','IOS') NOT NULL COMMENT '快照',
  `status`       ENUM('PENDING','RUNNING','PASSED','FAILED','ERROR','CANCELLED') NOT NULL DEFAULT 'PENDING',
  `total`        INT NOT NULL DEFAULT 0,
  `passed`       INT NOT NULL DEFAULT 0,
  `failed`       INT NOT NULL DEFAULT 0,
  `errored`      INT NOT NULL DEFAULT 0,
  `skipped`      INT NOT NULL DEFAULT 0,
  `started_at`   DATETIME NULL,
  `finished_at`  DATETIME NULL,
  `duration_ms`  BIGINT   NULL,
  -- M3.1：终态原因（进程重启中断 / 用户取消 / 队列满）
  `message`      VARCHAR(512) NULL,
  `created_by`   BIGINT   NULL,
  `created_at`   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_exec_project_time` (`project_id`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='执行批次';

-- ── 10. execution_step_result（含定位稳定性埋点 + 二期预留列）──
CREATE TABLE IF NOT EXISTS `execution_step_result` (
  `id`            BIGINT      NOT NULL AUTO_INCREMENT,
  `execution_id`  BIGINT      NOT NULL,
  `case_id`       BIGINT      NOT NULL,
  `step_id`       BIGINT      NULL,
  `seq`           INT         NOT NULL,
  `action_key`    VARCHAR(64) NOT NULL,
  `element_id`    BIGINT      NULL,
  `status`        ENUM('PASSED','FAILED','ERROR','SKIPPED') NOT NULL,
  -- M3.1：第几次尝试（重试每次一行，便于看到"第一次为什么失败"）
  `attempt`       INT         NOT NULL DEFAULT 1,
  `duration_ms`   INT         NULL,
  `message`       TEXT        NULL,
  -- ★ 让"哪条定位符最稳"成为可统计事实（二期自愈的数据基础）
  `used_locator_id` BIGINT    NULL COMMENT '★ 实际命中的定位符',
  `fallback_index`  INT       NULL COMMENT '★ 0=首选命中，>0=第 N 条回退命中',
  -- 二期 WebView 预留：M1 起就写入
  `active_platform` VARCHAR(16) NULL,
  `active_engine`   VARCHAR(64) NULL,
  `screenshot_artifact_id` BIGINT NULL,
  `created_at`    DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_result_exec` (`execution_id`),
  KEY `idx_result_locator` (`used_locator_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='步骤执行结果';

-- ── 11. report ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `report` (
  `id`           BIGINT      NOT NULL AUTO_INCREMENT,
  `execution_id` BIGINT      NOT NULL,
  `format`       VARCHAR(16) NOT NULL DEFAULT 'HTML',
  `path`         VARCHAR(512) NULL,
  `summary`      JSON        NULL,
  `created_at`   DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_report_execution_format` (`execution_id`, `format`),
  KEY `idx_report_exec` (`execution_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='执行报告';

-- ── 12. artifact ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `artifact` (
  `id`             BIGINT      NOT NULL AUTO_INCREMENT,
  `execution_id`   BIGINT      NULL,
  `step_result_id` BIGINT      NULL,
  `kind`           VARCHAR(32) NOT NULL DEFAULT 'SCREENSHOT',
  `storage`        VARCHAR(16) NOT NULL DEFAULT 'LOCAL',
  `path`           VARCHAR(512) NOT NULL,
  `size_bytes`     BIGINT      NULL,
  `created_at`     DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_artifact_exec` (`execution_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='产物（截图/trace/视频）';

SET FOREIGN_KEY_CHECKS = 1;
