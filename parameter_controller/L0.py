# noqa: N999
# from bytes_parser import Notification
# from pydantic import BaseModel, Field

# from parameter_controller.models import AlarmCondition, Qualifier


# def create_telegram_message(error: list[Notification],
#                             warnings: list[Notification]):
#     ...

# def L0_notification(error: list[Notification],
#                     warnings: list[Notification]):
#     create_telegram_message(error, warnings)


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

# def get_qualifier(sat_id: int, dev_id: int, frame_type: int) -> int:
#     return (sat_id << 8) | (dev_id << 4) | frame_type


# class L0_Map(BaseModel):
    # models: dict[int, dict[str, AlarmCondition | dict[str, AlarmCondition]]] = Field(default_factory=dict)
    # params: dict[int, list[str | tuple[str, list[str]]]] = Field(default_factory=dict)


# def create_models(L0_map: dict[int, dict[str, AlarmCondition | dict[str, AlarmCondition]]],
#                   params: list[str | tuple[str, list[str]]],
#                   qualifier: int):
#     if not params:
#         return
#     L0_map[qualifier] = {}
#     # q = Qualifier(value=qualifier,
#     #               sat_id=qualifier >> 8,
#     #               dev_id=(qualifier & 0xFF) >> 4,
#     #               frame_type=qualifier & 0x0F)
#     for param in params:
#         if isinstance(param, str):
#             L0_map[qualifier][param] = AlarmCondition(label=param)
#         else:
#             L0_map[qualifier][param[0]] = {
#                 p: AlarmCondition(label=param[0], bitfield=p)
#                 for p in param[1]
#             }



# def update_map(L0_map: L0_Map, sat_id: int, dev_id: int | tuple[int, ...],
#                frame_type: int, params: list[str | tuple[str, list[str]]]):
#     if isinstance(dev_id, tuple):
#         for d_id in dev_id:
#             qualifier = get_qualifier(sat_id, d_id, frame_type)
#             create_models(L0_map.models, params, qualifier)
#             L0_map.params[qualifier] = params
#     else:
#         qualifier = get_qualifier(sat_id, dev_id, frame_type)
#         create_models(L0_map.models, params, qualifier)
#         L0_map.params[qualifier] = params

# def create_flat_L0_map() -> L0_Map:
#     l0_map = L0_Map()
#     for sat_id, sat_id_dict in L0_MAP_CONFIG.items():
#         for dev_id, dev_id_dict in sat_id_dict.items():
#             for frame_type, params in dev_id_dict.items():
#                 if isinstance(sat_id, tuple):
#                     for s_id in sat_id:
#                         update_map(l0_map, s_id, dev_id, frame_type, params)
#                 else:
#                     update_map(l0_map, sat_id, dev_id, frame_type, params)
#     return l0_map


# if __name__ == '__main__':
#     l0_map = create_flat_L0_map()
#     for key, val in l0_map.models.items():
#         print(f'{key} {val}')