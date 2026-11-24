from datetime import UTC, datetime

from bytes_parser import Frame
from loguru import logger
from sat_frames import frames_map_0x02

from parameter_controller.L0.config import (
    L0_MAP_CONFIG,
    L0_MAP_TYPE_ALIAS,
    get_qualifier,
)
from parameter_controller.models import (
    L0_TrackedField,
    Qualifier,
    SatModel,
    SubsystemState,
    TMI_Status,
)


class ParamController:
    def __init__(self) -> None:
        self.state: dict[int, SatModel] = {}
        self.compare_onboard_time = False
        self.pending_operations: list[dict] = []

    def process_event(self, sat_id: int, dev_id: int, frame_type: int,
                      label: str, bitfield: str | None, username: str,
                      comment: str):
        qualifier: int = (sat_id << 16) | (dev_id << 12) | frame_type
        model: SatModel = self.state[sat_id]
        fields: dict = model.subsystems[dev_id].tmi[frame_type].L0_tracking_fields
        status_or_key: L0_TrackedField | dict[str, L0_TrackedField] = fields[label]

        if isinstance(status_or_key, dict) and bitfield:
            _field_label: str = f'{status_or_key}.{bitfield}'
            event: L0_TrackedField = status_or_key[bitfield]
        elif isinstance(status_or_key, L0_TrackedField) and not bitfield:
            _field_label = f'{status_or_key}'
            event = status_or_key
        else:
            logger.debug(f'Event not found for {label} {bitfield} '\
                         f'({sat_id}, {dev_id}, {frame_type}) tracked field')
            return
        now: datetime = datetime.now().astimezone()
        if event.status and event.status.priority == 3:
            event.status.user_comment = comment
            event.status.processed_by_user = username
            event.status.processed_at = now
            model.alarms.pending.pop(qualifier)
            model.alarms.processed.append(event.status)
            _field_path = f'subsystems.{dev_id}.tmi.{frame_type}.L0_tracking_fields.{_field_label}'
            self.pending_operations.append({
                '$set': {
                    f'{_field_path}.status.user_comment': f"{comment}",
                    f'{_field_path}.status.processed_by_user': f"{username}",
                    f'{_field_path}.status.processed_at': f"{now.isoformat()}"
                },
                '$pop': {
                    'alarms.pending': 1
                },
                '$push': {
                    'alarms.processed': event.status.model_dump()
                }
            })

    def load_config(self, l0_config: L0_MAP_TYPE_ALIAS, frames_map: dict):
        for sat_id, sat_id_dict in l0_config.items():
            if isinstance(sat_id, tuple):
                for s_id in sat_id:
                    sat_state = SatModel(label=frames_map[s_id]['label'],
                                         sat_id=s_id)
                    for dev_id, dev_id_dict in sat_id_dict.items():
                        sat_state.init_dev_id_from_config(s_id, dev_id,
                                                          dev_id_dict,
                                                          frames_map)
                    self.state[s_id] = sat_state
            else:
                sat_state = SatModel(label=frames_map[sat_id]['label'],
                                     sat_id=sat_id)
                for dev_id, dev_id_dict in sat_id_dict.items():
                    sat_state.init_dev_id_from_config(sat_id, dev_id,
                                                      dev_id_dict, frames_map)
                self.state[sat_id] = sat_state

    def on_received_data(self, hex_data: str, timestamp: datetime,
                         username: str, gs_label: str) -> list[L0_TrackedField]:
        bytes_data = bytes.fromhex(hex_data)
        sat_id, dev_id, flags, frame_type = get_qualifier(bytes_data)
        frame: Frame = frames_map_0x02[sat_id][dev_id][flags][frame_type]
        if flags == 1:
            logger.debug(f'Frame has incorrect flag: {hex_data}')
            return []
        frame.parse(hex_data)
        if not frame.rows[-1]._is_valid:
            logger.debug(f'Frame has invalid CRC: {hex_data}')
            return []  # CRC16 is not valid
        onboard_time: datetime = datetime.fromisoformat(frame.rows_dict['Время кадра']._repr_data)
        if self.compare_onboard_time:
            if onboard_time > timestamp and (onboard_time - timestamp).seconds > 5:
                logger.debug(f'Onboard and GS time delta: {(onboard_time - timestamp).seconds}')
                return []
            if onboard_time < timestamp and (timestamp - onboard_time).seconds > 5:
                logger.debug(f'Onboard and GS time delta: {(timestamp - onboard_time).seconds}')
                return []

        sat: SatModel | None = self.state.get(sat_id)
        if not sat:
            sat = SatModel(label=frames_map_0x02[sat_id]['label'],
                           sat_id=sat_id)
            self.state[sat_id] = sat
            # self.pending_operations.append({'$set': })

        sat.last_user = username
        sat.last_gs = gs_label
        sat.last_session = timestamp

        subsystem: SubsystemState | None = sat.subsystems.get(dev_id)
        if not subsystem:
            subsystem = SubsystemState(sat_id=sat_id, dev_id=dev_id,
                                       label=frames_map_0x02[sat_id][dev_id]['label'])
            self.pending_operations.append({
                '$push': {
                    'subsystems': {f'{dev_id}': subsystem.model_dump()}
                }
            })
        subsystem.last_update = timestamp

        tmi: TMI_Status | None = subsystem.tmi.get(frame_type)
        if not tmi:
            q = Qualifier(sat_id=sat_id, dev_id=dev_id,
                          frame_type=frame_type)
            tmi = TMI_Status(qualifier=q, name=frame.frame_type)

        about_to_notify: list[L0_TrackedField] = tmi.add_tmi(hex_data, timestamp, frame)
        tmi.update_tracked_fields_history(timestamp, frame)
        qualifier: int = int.from_bytes(bytes_data[2:6], 'little')
        for field in about_to_notify:
            if field.status and field.status.priority == 3:
                sat.alarms.pending.setdefault(qualifier, field.status)
        return about_to_notify




if __name__ == '__main__':
    controller = ParamController()
    controller.load_config(L0_MAP_CONFIG, frames_map_0x02)

    pss_tmi0 = "F1 0F 65 80 00 30 00 00 13 92 74 32 03 00 00 00 01 00 03 17 00 00 00 00 00 00 00 09 01 00 00 FE 00 00 00 90 40 A9 40 88 40 A2 40 27 00 00 00 26 00 00 00 90 40 9B 30 00 00 16 1B 00 00 FF 93 03 03 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 AA 2C"
    pss_tmi0_b = bytearray.fromhex(pss_tmi0)
    pss_tmi0_b[36] = 0
    pss_tmi0 = pss_tmi0_b.hex(" ").upper()
    data = [
        pss_tmi0,
        "F1 0F 65 80 02 30 00 00 13 92 74 32 03 00 15 21 FE 00 00 00 00 00 00 00 0C 07 00 00 09 00 00 C2 40 CB 40 C5 40 F6 00 D4 00 E1 00 C8 40 42 40 EB FF 46 00 E6 FF 00 00 00 00 00 00 55 01 32 00 04 00 0C 00 00 00 00 00 0C 00 00 00 00 00 00 00 F8 F7 00 00 FD FD 00 00 F4 F1 F2 F0 F5 F3 F3 F1 F3 F3 F9 F9 EA EA E6 E6 00 00 00 00 00 00 00 00 F8 FF F2 F3 F6 E8 00 00 00 00 00 00 00 00 00 B6 25",
        "F1 0F 65 80 00 30 00 00 13 92 74 32 03 00 00 00 01 00 03 17 00 00 00 00 00 00 00 09 01 00 00 FE 00 00 00 90 40 A9 40 88 40 A2 40 27 00 00 00 26 00 00 00 90 40 9B 30 00 00 16 1B 00 00 FF 93 03 03 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 AA 2C",
    ]
    for frame in data:
        result = controller.on_received_data(frame, datetime.now(UTC), 'admin', 'NSU')
        for r in result:
            print(r)
    # print(controller.state[0x65].model_dump_json(indent=4))