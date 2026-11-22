from datetime import datetime

from bytes_parser import Notification
from frames_parser import frames_map, get_frame
from sat_frames import frames_map_0x02

from parameter_controller.L0 import (
    L0_Map,
    create_flat_L0_map,
    get_qualifier,
)
from parameter_controller.models import (
    AlarmCondition,
    SatModel,
    SubsystemState,
    TMI_Model,
    TMI_Status,
)

frames_map[0x02].update(frames_map_0x02)


class ParamController:
    def __init__(self) -> None:
        self.state: dict[int, SatModel] = {}
        self.L0: L0_Map = create_flat_L0_map()

    def update_parameters(self, ts: datetime, qualifier: int,
                          notifications: list[Notification]) -> list[AlarmCondition]:
        about_to_notify: list[AlarmCondition] = []
        for notification in notifications:
            field = self.L0.models[qualifier][notification.row.label]
            if isinstance(field, AlarmCondition):
                if field.update_data(ts, notification.row):
                    about_to_notify.append(field)
            else:
                for bit in notification.bitfield:
                    bitfield_alarm: AlarmCondition = field[bit.label]
                    if bitfield_alarm.update_data(ts, bit):
                        about_to_notify.append(bitfield_alarm)
        return about_to_notify

    def on_received_data(self, model: TMI_Model):
        frame, qualifier = get_frame(bytes.fromhex(model.raw_data), frames_map)
        sat_id_val, sat_id_label = qualifier[1]
        dev_id_val, dev_id_label = qualifier[2]
        flag_val, _ = qualifier[3]
        frame_type_val, frame_type_label = qualifier[4]
        if flag_val == 1:
            return
        frame.parse(model.raw_data)
        if not frame.rows[-1]._is_valid:
            return  # CRC16 is not valid
        onboard_time: datetime = datetime.fromisoformat(frame['Время кадра']._repr_data)
        if onboard_time > model.timestamp and (onboard_time - model.timestamp).seconds > 5:
            return
        if onboard_time < model.timestamp and (model.timestamp - onboard_time).seconds > 5:
            return

        qualifier = get_qualifier(sat_id_val, dev_id_val, frame_type_val)
        params: list[str | tuple[str, list[str]]] = self.L0.params[qualifier]
        errors, warnings = frame.get_failed_params(params)
        about_to_notify: list[AlarmCondition] = []
        about_to_notify.extend(self.update_parameters(model.timestamp, qualifier, errors))
        about_to_notify.extend(self.update_parameters(model.timestamp, qualifier, warnings))

        sat: SatModel | None = self.state.get(sat_id_val)
        if not sat:
            sat = SatModel(label=sat_id_label, sat_id=sat_id_val)
            self.state[sat_id_val] = sat

        sat.last_user = model.username
        sat.last_gs = model.gs_label
        sat.last_session = model.timestamp

        subsystem = sat.subsystems.get(dev_id_val)
        if not subsystem:
            subsystem = SubsystemState(dev_id=dev_id_val, label=dev_id_label)
        subsystem.last_update = model.timestamp

        tmi = subsystem.tmi.get(frame_type_val)
        if not tmi:
            tmi = TMI_Status(frame_type=frame_type_val, name=frame_type_label)
        tmi.add_tmi(model.raw_data, model.timestamp)



if __name__ == '__main__':
    ...