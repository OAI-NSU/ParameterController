from datetime import datetime

from frames_parser import frames_map, get_frame
from sat_frames import frames_map_0x02

from parameter_controller.L0 import L0_MAP_CONFIG, L0_MAP_TYPE_ALIAS
from parameter_controller.models import (
    AlarmCondition,
    Qualifier,
    SatModel,
    SubsystemState,
    TMI_Status,
)

frames_map[0x02].update(frames_map_0x02)


class ParamController:
    def __init__(self) -> None:
        self.state: dict[int, SatModel] = {}
        self.load_config(L0_MAP_CONFIG, frames_map[0x02])

    def load_config(self, l0_config: L0_MAP_TYPE_ALIAS, frames_map: dict):
        for sat_id, sat_id_dict in l0_config.items():
            if isinstance(sat_id, tuple):
                for s_id in sat_id:
                    sat_state = SatModel(label=frames_map[s_id]['label'], sat_id=s_id)
                    for dev_id, dev_id_dict in sat_id_dict.items():
                        sat_state.init_dev_id_from_config(s_id, dev_id, dev_id_dict, frames_map)
                    self.state[s_id] = sat_state
            else:
                sat_state = SatModel(label=frames_map[sat_id]['label'], sat_id=sat_id)
                for dev_id, dev_id_dict in sat_id_dict.items():
                    sat_state.init_dev_id_from_config(sat_id, dev_id, dev_id_dict, frames_map)
                self.state[sat_id] = sat_state

    def on_received_data(self, hex_data: str, timestamp: datetime, username: str, gs_label: str):
        frame, qualifier = get_frame(bytes.fromhex(hex_data), frames_map)
        sat_id_val, sat_id_label = qualifier[1]
        dev_id_val, dev_id_label = qualifier[2]
        flag_val, _ = qualifier[3]
        frame_type_val, frame_type_label = qualifier[4]
        if flag_val == 1:
            return
        frame.parse(hex_data)
        if not frame.rows[-1]._is_valid:
            return  # CRC16 is not valid
        onboard_time: datetime = datetime.fromisoformat(frame['Время кадра']._repr_data)
        if onboard_time > timestamp and (onboard_time - timestamp).seconds > 5:
            return
        if onboard_time < timestamp and (timestamp - onboard_time).seconds > 5:
            return

        sat: SatModel | None = self.state.get(sat_id_val)
        if not sat:
            sat = SatModel(label=sat_id_label, sat_id=sat_id_val)
            self.state[sat_id_val] = sat

        sat.last_user = username
        sat.last_gs = gs_label
        sat.last_session = timestamp

        subsystem: SubsystemState | None = sat.subsystems.get(dev_id_val)
        if not subsystem:
            subsystem = SubsystemState(sat_id=sat_id_val, dev_id=dev_id_val,
                                       label=dev_id_label)
        subsystem.last_update = timestamp

        tmi: TMI_Status | None = subsystem.tmi.get(frame_type_val)
        if not tmi:
            q = Qualifier(sat_id=sat_id_val, dev_id=dev_id_val,
                          frame_type=frame_type_val)
            tmi = TMI_Status(qualifier=q, name=frame_type_label)

        params: list[str | tuple[str, tuple[str, ...]]] = tmi.get_tracking_labels()
        errors, warnings = frame.get_failed_params(params)
        about_to_notify: list[AlarmCondition] = tmi.add_tmi(hex_data,
                                                            timestamp,
                                                            [*errors, *warnings])
        return about_to_notify




if __name__ == '__main__':
    controller = ParamController()
    print(controller.state[0x65].model_dump_json(indent=4))