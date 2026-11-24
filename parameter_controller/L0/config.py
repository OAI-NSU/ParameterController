from collections import defaultdict


def nested_dict():
    return defaultdict(nested_dict)


L0_MAP_TYPE_ALIAS = dict[int | tuple[int, ...],
                         dict[int | tuple[int, ...],
                              dict[int, list[str | tuple[str, list[str]]]]]]

L0_MAP_CONFIG: L0_MAP_TYPE_ALIAS = {
    (101, 102, 103, 104): {
        (1, 2): {
            0: [
                'Модуль угловой скорости в СК КА, dps',
                ('Статус модуля СОП1', ['MCU_temp'])
            ],
        },
        3: {
            0: [
                'Напряжение VBAT1',
                'Напряжение VBAT2'
            ]
        },
        (6, 7): {
            0: [
                'Модуль угловой скорости в СК КА, dps',
                ('Статус модуля СОП', ['MCU_temp']),
            ],
            4: [
                'Температура платы СОП',
                'Напряжение подсистемы СОП, mV',
                'Напряжение ДСГ, mV'
            ]
        }
    }
}

# def get_params(sat_id: int, dev_id: int, frame_type: int):
#     for sat_id_key in L0_MAP_CONFIG:
#         if (isinstance(sat_id_key, tuple) and sat_id in sat_id_key) or sat_id_key == sat_id:
#             for dev_id_key in L0_MAP_CONFIG[sat_id_key]:
#                 if (isinstance(dev_id_key, tuple) and dev_id in dev_id_key) or dev_id == dev_id_key:
#                     return L0_MAP_CONFIG[sat_id_key][dev_id_key][frame_type]
#     return []

def iterate_tmi(model: type, sat_id: int, dev_id: int, frame_type: int,
                frames_map: dict, params: list[str | tuple[str, list[str]]],
                params_map: defaultdict):
    if not params:
        return
    tmi_name: str = frames_map[sat_id][dev_id][0][frame_type].frame_type
    sat_label: str = frames_map[sat_id]['label']
    dev_id_label: str = frames_map[sat_id][dev_id]['label']
    params_map[sat_id][dev_id][frame_type] = params
    for param in params:
        if isinstance(param, str):
            yield model(sat_label=sat_label,
                        dev_label=dev_id_label,
                        frame_label=tmi_name,
                        field_label=param,
                        sat_id=sat_id,
                        dev_id=dev_id,
                        frame_type=frame_type)
        else:
            for p in param[1]:
                yield model(sat_label=sat_label,
                            dev_label=dev_id_label,
                            frame_label=tmi_name,
                            field_label=param[0],
                            bitfield=p,
                            sat_id=sat_id,
                            dev_id=dev_id,
                            frame_type=frame_type)

def iterate_dev_id(model: type, sat_id: int, dev_id: int | tuple[int, ...],
                   dev_id_dict: dict[int, list[str | tuple[str, list[str]]]],
                   frames_map: dict, params_map: defaultdict):
    if isinstance(dev_id, tuple):
        for d_id in dev_id:
            for frame_type, params in dev_id_dict.items():
                yield from iterate_tmi(model, sat_id, d_id, frame_type,
                                       frames_map, params, params_map)
    else:
        for frame_type, params in dev_id_dict.items():
            yield from iterate_tmi(model, sat_id, dev_id, frame_type,
                                   frames_map, params, params_map)

def load_config(model: type, frames_map: dict, params_map: defaultdict):
    for sat_id, sat_id_dict in L0_MAP_CONFIG.items():
        if isinstance(sat_id, tuple):
            for s_id in sat_id:
                for dev_id, dev_id_dict in sat_id_dict.items():
                    yield from iterate_dev_id(model, s_id, dev_id, dev_id_dict,
                                              frames_map, params_map)
        else:
            for dev_id, dev_id_dict in sat_id_dict.items():
                yield from iterate_dev_id(model, sat_id, dev_id, dev_id_dict,
                                          frames_map, params_map)

def get_qualifier(raw_frame: bytes):
    """
    ====================================  FRAME QUALIFIER FORMAT  =====================================
    |_________________________________________________________________________________________________|
    |        HI Byte         |      Low Byte    |           HI Byte         |         Low Byte        |
    |___________________ ____|__________________|___________________________|_________________________|
    |  7  6   |  5 4 3 2 1 0   7 6 5 4 3 2 1 0  |  7  6  5  4 |  3  2  1  0 |  7  6  5  4  3  2  1  0 |
    |_________|_________________________________|_____________|_____________|_________________________|
    | modifier|         SAT_ID (14 bits)        |  Dev_ID     |   Flags     |        FrameType        |
    |_________|_________________________________|_____________|_____________|_________________________|

    """
    if len(raw_frame) != 128:
        raise ValueError(f'Incorrect frame size: {len(raw_frame)}. '\
                         f'Must be 128')
    order = ('big', 'little')[raw_frame.startswith(b'\xf1\x0f')]
    sat_id = int.from_bytes(raw_frame[2:4], order ) & 0x3FFF
    _loc_id = int.from_bytes(raw_frame[4:6], order )
    dev_id = (_loc_id & 0xF000) >> 12
    loc_id = _loc_id & 0x0FFF
    flags = (loc_id & 0x0F00) >> 8
    frame_type = loc_id & 0xFF
    return sat_id, dev_id, flags, frame_type

