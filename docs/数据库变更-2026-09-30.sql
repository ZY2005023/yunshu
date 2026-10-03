-- =============================================================================
-- 云舒 · 数据库变更脚本
-- 变更日期：2026-09-30
-- 对应改造：P0-4「危机干预兜底」
--
-- 执行方式（二选一）：
--   命令行： mysql -u root -p mental_health_assistant < 数据库变更-2026-09-30.sql
--   图形化： 用 Navicat/DataGrip 打开本文件，选中全部后执行
--
-- 说明：本次只新增一张表，不改动任何已有表结构，可安全重复执行（IF NOT EXISTS）。
-- =============================================================================

USE `mental_health_assistant`;

-- -----------------------------------------------------------------------------
-- 危机预警事件表
-- 作用：只要规则层（关键词）或模型层（AI riskLevel）判定存在风险，就落一条记录，
--       由管理端工单跟进处置。避免"检测到风险却没有任何痕迹与后续动作"。
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `crisis_event` (
  `id`              bigint       NOT NULL AUTO_INCREMENT COMMENT '事件ID',
  `user_id`         bigint       NOT NULL COMMENT '触发用户ID',
  `session_id`      bigint       NULL DEFAULT NULL COMMENT '关联咨询会话ID（日记触发为空）',
  `diary_id`        bigint       NULL DEFAULT NULL COMMENT '关联情绪日记ID（对话触发为空）',
  `source`          varchar(20)  NOT NULL COMMENT '来源：CHAT 咨询对话 / DIARY 情绪日记',
  `level`           tinyint      NOT NULL COMMENT '风险等级 1=关注 2=预警 3=危机',
  `trigger_type`    varchar(20)  NOT NULL COMMENT '触发方式：KEYWORD 规则命中 / LLM 模型判定',
  `matched_terms`   varchar(500) NULL DEFAULT NULL COMMENT '命中的关键词，逗号分隔',
  `content_snippet` varchar(500) NULL DEFAULT NULL COMMENT '触发内容片段（截断保存）',
  `status`          varchar(20)  NOT NULL DEFAULT 'PENDING' COMMENT '处置状态：PENDING 待处理 / HANDLING 处理中 / RESOLVED 已处置 / IGNORED 已忽略',
  `handler_id`      bigint       NULL DEFAULT NULL COMMENT '处置人ID',
  `handle_note`     varchar(500) NULL DEFAULT NULL COMMENT '处置说明',
  `handled_at`      datetime     NULL DEFAULT NULL COMMENT '处置时间',
  `created_at`      datetime     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at`      datetime     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_user_created`(`user_id` ASC, `created_at` ASC) USING BTREE,
  INDEX `idx_status_level`(`status` ASC, `level` ASC) USING BTREE,
  INDEX `idx_created_at`(`created_at` ASC) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '危机预警事件（合规留痕）';

-- -----------------------------------------------------------------------------
-- 校验：执行后应能查到表结构
-- -----------------------------------------------------------------------------
-- SHOW CREATE TABLE `crisis_event`;
