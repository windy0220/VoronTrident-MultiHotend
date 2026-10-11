# 喷嘴对齐 / 停靠位定位校准模块
#
# 多热端停靠坞定位校准
#
# 改编自原先使用的代码：
# Klipper_ToolChanger / probe_multi_axis.py
#
# 该校准通过比较校准动作前后 CoreXY 步进电机 MCU 位置，
# 来确定停靠位位置。
#
# 停靠位计算：
#
#   X = X endstop + 计算出的 X 偏移
#   Y = Y endstop + 计算出的 Y 偏移
#
# 校准动作本身不会从最终停靠位坐标中扣除。


import logging


class DockLocateCalibrate:

    def __init__(self, config):

        self.printer = config.get_printer()
        self.name = config.get_name()

        # ----------------------------------------------------
        # 配置
        # ----------------------------------------------------

        # 每个 MCU 步对应的毫米数。
        self.xy_resolution = config.getfloat('xy_resolution')

        # 打印机实际的回零/止挡位置。
        #
        # 这些值应与以下配置对应：
        #
        # [stepper_x]
        # position_endstop:
        #
        # [stepper_y]
        # position_endstop:
        #
        # 它们不是床尺寸，也不是 position_max。
        self.x_endstop = config.getfloat('x_endstop')
        self.y_endstop = config.getfloat('y_endstop')

        # 校准动作的移动距离。
        # self.calibrate_move_x = config.getfloat(
        #     'calibrate_move_x'
        # )

        # ----------------------------------------------------
        # Klipper 对象
        # ----------------------------------------------------

        self.gcode = self.printer.lookup_object('gcode')

        # 加载校准动作模板。
        gcode_macro = self.printer.load_object(
            config,
            'gcode_macro'
        )

        self.calibrate_move_template = gcode_macro.load_template(
            config,
            'dock_calibrate_move_gcode',
            ''
        )

        # ----------------------------------------------------
        # 注册 G-Code 命令
        # ----------------------------------------------------

        self.gcode.register_command(
            'DOCK_LOCATE_CALIBRATE',
            self.cmd_DOCK_LOCATE_CALIBRATE,
            desc=self.cmd_DOCK_LOCATE_CALIBRATE_help
        )

    # --------------------------------------------------------
    # 状态
    # --------------------------------------------------------

    def get_status(self, eventtime):
        return {}

    # --------------------------------------------------------
    # 获取 MCU 步进电机位置
    # --------------------------------------------------------

    def get_mcu_position(self):

        toolhead = self.printer.lookup_object('toolhead')
        steppers = toolhead.kin.get_steppers()

        mcu_pos_x = None
        mcu_pos_y = None

        for stepper in steppers:

            name = stepper.get_name()

            if name == "stepper_x":
                mcu_pos_x = stepper.get_mcu_position()

            elif name == "stepper_y":
                mcu_pos_y = stepper.get_mcu_position()

        if mcu_pos_x is None or mcu_pos_y is None:
            raise self.printer.command_error(
                "无法获取 X/Y MCU 步进电机位置"
            )

        return {
            'x': mcu_pos_x,
            'y': mcu_pos_y
        }

    # --------------------------------------------------------
    # 校准命令
    # --------------------------------------------------------

    cmd_DOCK_LOCATE_CALIBRATE_help = (
        "计算 Lineux Hotswap 停靠位位置"
    )

    def cmd_DOCK_LOCATE_CALIBRATE(self, gcmd):

        # ----------------------------------------------------
        # 获取用户变量
        # ----------------------------------------------------

        user_variables = self.printer.lookup_object(
            'gcode_macro _User_Variables'
        )

        # ----------------------------------------------------
        # 校准期间禁用工具停靠
        # ----------------------------------------------------

        user_variables.variables['skip_homing_park'] = True

        try:

            # ------------------------------------------------
            # 记录初始 MCU 位置
            # ------------------------------------------------

            initial_res = self.get_mcu_position()

            logging.info(
                "Lineux Dock Calibration - "
                "Initial MCU position: X=%s Y=%s",
                initial_res['x'],
                initial_res['y']
            )

            # ------------------------------------------------
            # 执行校准动作
            # ------------------------------------------------

            self.calibrate_move_template.run_gcode_from_command()

            # ------------------------------------------------
            # 记录最终 MCU 位置
            # ------------------------------------------------

            final_res = self.get_mcu_position()

            logging.info(
                "Lineux Dock Calibration - "
                "Final MCU position: X=%s Y=%s",
                final_res['x'],
                final_res['y']
            )

            # ------------------------------------------------
            # 计算 MCU 移动量
            # ------------------------------------------------

            dx = final_res['x'] - initial_res['x']
            dy = final_res['y'] - initial_res['y']

            # ------------------------------------------------
            # 计算原始停靠位偏移
            #
            # CoreXY 关系：
            #
            #   X = -(dx + dy) / 2
            #   Y = -(dx - dy) / 2
            #
            # 然后将 MCU 步数转换为毫米。
            # ------------------------------------------------

            raw_dock_x = (
                -((dx + dy) / 2.0)
                * self.xy_resolution
            )

            raw_dock_y = (
                -((dx - dy) / 2.0)
                * self.xy_resolution
            )

            # ------------------------------------------------
            # 计算实际停靠位坐标
            #
            # 校准动作本身不会从最终坐标中扣除。
            # ------------------------------------------------

            dock_x = self.x_endstop + raw_dock_x
            dock_y = self.y_endstop + raw_dock_y

            # ------------------------------------------------
            # 报告结果
            # ------------------------------------------------

            gcmd.respond_info(
                "多热端停靠坞定位校准\n"
                "--------------------------------\n"
                "初始 MCU: X=%s Y=%s\n"
                "最终 MCU: X=%s Y=%s\n"
                "MCU 变化量: X=%s Y=%s\n"
                "XY 分辨率: %.7f mm/step\n"
                "X Endstop: %.2f mm\n"
                "Y Endstop: %.2f mm\n"
                # "校准移动: %.2f mm\n"
                "原始偏移: X=%.2f Y=%.2f mm\n"
                "计算出的停靠位位置:\n"
                "X: %.2f mm\n"
                "Y: %.2f mm"
                % (
                    initial_res['x'],
                    initial_res['y'],
                    final_res['x'],
                    final_res['y'],
                    dx,
                    dy,
                    self.xy_resolution,
                    self.x_endstop,
                    self.y_endstop,
                    # self.calibrate_move_x,
                    raw_dock_x,
                    raw_dock_y,
                    dock_x,
                    dock_y
                )
            )

        finally:

            # ------------------------------------------------
            # 重新启用正常工具停靠
            # ------------------------------------------------

            user_variables.variables['skip_homing_park'] = False


# ------------------------------------------------------------
# Klipper 模块加载器
# ------------------------------------------------------------

def load_config(config):
    return DockLocateCalibrate(config)