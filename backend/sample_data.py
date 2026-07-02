"""Синтетический, но предметно точный датасет R&D-графа для горно-металлургической
отрасли. Покрывает 4 официальных примера запросов из ТЗ хакатона, включая
намеренный пробел в данных (холодный климат + кучное выщелачивание + никелевая руда)
и пару противоречащих друг другу выводов (скорость циркуляции католита).

Реальный корпус документов (Яндекс.Диск) недоступен из песочницы выполнения —
датасет собран вручную по образцу того, что должен извлекать NLP-пайплайн
(backend/extraction.py, roadmap) из реальных отчётов/статей/патентов.
"""
from __future__ import annotations

from backend.graph_store import GraphStore
from backend.schema import Entity, EntityType, Relation, RelationType

# ---------------------------------------------------------------------------
# Справочники
# ---------------------------------------------------------------------------

MATERIALS = [
    ("mat_process_water", "Оборотная вода обогатительной фабрики"),
    ("mat_permeate", "Пермеат (умягчённая вода)"),
    ("mat_nickel_cathode", "Никелевый катод"),
    ("mat_catholyte", "Католит"),
    ("mat_anolyte", "Анолит"),
    ("mat_copper_matte", "Медный штейн"),
    ("mat_nickel_matte", "Никелевый штейн"),
    ("mat_slag", "Шлак"),
    ("mat_nickel_ore", "Никелевая руда (окисленная)"),
    ("mat_copper_ore", "Медная руда (сульфидная)"),
    ("mat_mine_water", "Шахтная вода"),
    ("mat_gypsum", "Техногенный гипс"),
]

PROCESSES = [
    ("proc_ro", "Обратный осмос"),
    ("proc_ion_exchange", "Ионный обмен"),
    ("proc_electrodialysis", "Электродиализ"),
    ("proc_lime_soda", "Известково-содовое умягчение"),
    ("proc_electrowinning_ni", "Электроэкстракция никеля"),
    ("proc_smelting_cu", "Плавка медного концентрата на штейн"),
    ("proc_smelting_ni", "Плавка никелевого концентрата на штейн"),
    ("proc_heap_leaching", "Кучное выщелачивание"),
    ("proc_deep_injection", "Закачка в глубокие горизонты"),
]

CONDITIONS = [
    ("cond_cold", "Холодный климат"),
    ("cond_temperate", "Умеренный климат"),
    ("cond_arid", "Аридный климат"),
]

PROPERTIES = [
    ("prop_dry_residue", "Сухой остаток"),
    ("prop_catholyte_flow", "Скорость циркуляции католита"),
    ("prop_au_distribution", "Коэффициент распределения Au"),
    ("prop_ag_distribution", "Коэффициент распределения Ag"),
    ("prop_pgm_distribution", "Коэффициент распределения МПГ"),
    ("prop_techno_economic", "Технико-экономические показатели"),
    ("prop_extraction_rate", "Степень извлечения металла"),
]

EQUIPMENT = [
    ("eq_ro_unit", "Установка обратного осмоса"),
    ("eq_ew_cell_diaphragm", "Ванна электроэкстракции с диафрагменными ячейками"),
    ("eq_ew_cell_open", "Ванна электроэкстракции без диафрагмы"),
    ("eq_flash_furnace", "Печь взвешенной плавки (ПВП)"),
    ("eq_deep_well", "Скважина глубокого заложения"),
    ("eq_heap_pad", "Штабель кучного выщелачивания"),
]

FACILITIES = [
    ("fac_concentrator_norilsk", "Обогатительная фабрика №3 (Норильск)", "RU"),
    ("fac_concentrator_escondida", "Concentrator Plant (Escondida, Чили)", "INTL"),
    ("fac_smelter_monchegorsk", "Медно-никелевый комбинат (Мончегорск)", "RU"),
    ("fac_smelter_sudbury", "Smelter Complex (Sudbury, Канада)", "INTL"),
    ("fac_mine_kuzbass", "Угольная шахта (Кузбасс)", "RU"),
    ("fac_mine_germany", "Steinkohle Mine (Рурский бассейн, Германия)", "INTL"),
    ("fac_heap_site_ru", "Опытный полигон КВ (Забайкалье)", "RU"),
]

TEAMS = [
    ("team_water_lab", "Лаборатория водоподготовки"),
    ("team_hydromet", "Лаборатория гидрометаллургии"),
    ("team_pyromet", "Лаборатория пирометаллургии"),
    ("team_geotech", "Группа геотехнологий и закачки вод"),
]

EXPERTS = [
    ("expert_smirnova", "Смирнова И.П.", "team_water_lab"),
    ("expert_baranov", "Баранов Д.С.", "team_hydromet"),
    ("expert_li", "Li Wei", "team_pyromet"),
    ("expert_johansson", "Johansson E.", "team_hydromet"),
    ("expert_kowalski", "Kowalski T.", "team_geotech"),
    ("expert_fedorov", "Фёдоров А.В.", "team_geotech"),
]

TOPICS = [
    ("topic_water", "Водоподготовка и обессоливание"),
    ("topic_electrowinning", "Электроэкстракция"),
    ("topic_smelting", "Плавка и распределение металлов"),
    ("topic_leaching", "Выщелачивание"),
    ("topic_mine_water", "Шахтные и рудничные воды"),
]

# (id, title, date, country, confidence, topic_ids)
PUBLICATIONS = [
    ("pub_ro_2022", "Опыт применения обратного осмоса для доочистки оборотной воды ОФ", "2022-04-12", "RU", "высокая", ["topic_water"]),
    ("pub_ix_2021", "Ионообменное умягчение технической воды: пилотные испытания", "2021-09-03", "RU", "средняя", ["topic_water"]),
    ("pub_ed_2020", "Electrodialysis for process water desalination in mineral processing", "2020-11-20", "INTL", "высокая", ["topic_water"]),
    ("pub_ls_2019", "Известково-содовое умягчение: ограничения метода при повышенной сульфатности", "2019-05-15", "RU", "средняя", ["topic_water"]),
    ("pub_ew_ru_2023", "Циркуляция католита при электроэкстракции никеля: опыт комбината", "2023-02-08", "RU", "высокая", ["topic_electrowinning"]),
    ("pub_ew_intl_2022", "Catholyte flow optimization in nickel electrowinning cells", "2022-07-01", "INTL", "высокая", ["topic_electrowinning"]),
    ("pub_smelt_cu_2023", "Распределение благородных металлов между медным штейном и шлаком", "2023-10-11", "RU", "высокая", ["topic_smelting"]),
    ("pub_smelt_ni_2022", "PGM and gold distribution between nickel matte and slag in flash smelting", "2022-03-19", "INTL", "высокая", ["topic_smelting"]),
    ("pub_smelt_cu_2021", "Влияние состава шихты на извлечение серебра в штейн", "2021-06-06", "RU", "средняя", ["topic_smelting"]),
    ("pub_heap_cu_2021", "Кучное выщелачивание медных руд в условиях умеренного климата", "2021-08-14", "RU", "средняя", ["topic_leaching"]),
    ("pub_deep_inj_ru_2020", "Закачка шахтных вод в глубокие горизонты: опыт угольных бассейнов России", "2020-02-27", "RU", "средняя", ["topic_mine_water"]),
    ("pub_deep_inj_de_2019", "Deep well injection of mine water: German experience", "2019-12-05", "INTL", "высокая", ["topic_mine_water"]),
]

AUTHORS = {
    "pub_ro_2022": ["expert_smirnova"],
    "pub_ix_2021": ["expert_smirnova"],
    "pub_ed_2020": ["expert_johansson"],
    "pub_ls_2019": ["expert_smirnova"],
    "pub_ew_ru_2023": ["expert_baranov"],
    "pub_ew_intl_2022": ["expert_johansson"],
    "pub_smelt_cu_2023": ["expert_li"],
    "pub_smelt_ni_2022": ["expert_johansson"],
    "pub_smelt_cu_2021": ["expert_li"],
    "pub_heap_cu_2021": ["expert_baranov"],
    "pub_deep_inj_ru_2020": ["expert_fedorov"],
    "pub_deep_inj_de_2019": ["expert_kowalski"],
}

# ---------------------------------------------------------------------------
# Эксперименты
# каждый: id, publication_id, materials[], process_id, condition_id|None,
#         equipment_id|None, facility_id, property_ids[], numeric attrs,
#         effect, conclusion, contradiction_note|None, team_id, date, country, confidence
# ---------------------------------------------------------------------------

EXPERIMENTS = [
    dict(
        id="exp_ro_01", pub="pub_ro_2022",
        materials=["mat_process_water", "mat_permeate"], process="proc_ro",
        equipment="eq_ro_unit", facility="fac_concentrator_norilsk",
        props=["prop_dry_residue"],
        attrs={"sulfate_mg_l": 260, "chloride_mg_l": 240, "calcium_mg_l": 220, "magnesium_mg_l": 210, "sodium_mg_l": 230, "dry_residue_mg_l": 450},
        effect="Сухой остаток снижен с ~3500 до 450 мг/дм³ при исходных сульфатах/хлоридах/Ca/Mg/Na на уровне 200-260 мг/л",
        conclusion="Обратный осмос устойчиво даёт сухой остаток ниже 1000 мг/дм³ при указанном составе воды — рекомендован как основной метод.",
        team="team_water_lab", date="2022-03-01", country="RU", confidence="высокая",
    ),
    dict(
        id="exp_ix_01", pub="pub_ix_2021",
        materials=["mat_process_water", "mat_permeate"], process="proc_ion_exchange",
        equipment=None, facility="fac_concentrator_norilsk",
        props=["prop_dry_residue"],
        attrs={"sulfate_mg_l": 280, "chloride_mg_l": 250, "calcium_mg_l": 240, "magnesium_mg_l": 200, "sodium_mg_l": 260, "dry_residue_mg_l": 800},
        effect="Сухой остаток снижен до 800 мг/дм³, но требуется частая регенерация смолы",
        conclusion="Ионный обмен укладывается в требование ≤1000 мг/дм³, но эксплуатационные затраты выше, чем у обратного осмоса.",
        team="team_water_lab", date="2021-08-01", country="RU", confidence="средняя",
    ),
    dict(
        id="exp_ed_01", pub="pub_ed_2020",
        materials=["mat_process_water", "mat_permeate"], process="proc_electrodialysis",
        equipment=None, facility="fac_concentrator_escondida",
        props=["prop_dry_residue"],
        attrs={"sulfate_mg_l": 300, "chloride_mg_l": 270, "calcium_mg_l": 250, "magnesium_mg_l": 220, "sodium_mg_l": 280, "dry_residue_mg_l": 950},
        effect="Dry residue reduced to 950 mg/dm3 at similar feed composition",
        conclusion="Электродиализ применим при указанных концентрациях, но ближе к верхней границе допустимого сухого остатка.",
        team="team_water_lab", date="2020-10-15", country="INTL", confidence="высокая",
    ),
    dict(
        id="exp_ls_01", pub="pub_ls_2019",
        materials=["mat_process_water", "mat_gypsum"], process="proc_lime_soda",
        equipment=None, facility="fac_concentrator_norilsk",
        props=["prop_dry_residue"],
        attrs={"sulfate_mg_l": 290, "chloride_mg_l": 260, "calcium_mg_l": 230, "magnesium_mg_l": 215, "sodium_mg_l": 240, "dry_residue_mg_l": 1500},
        effect="Сухой остаток снижен только до 1500 мг/дм³, требование ≤1000 не достигнуто",
        conclusion="Известково-содовое умягчение НЕ подходит при сульфатности ≥250 мг/л — не обеспечивает нужный сухой остаток.",
        team="team_water_lab", date="2019-04-01", country="RU", confidence="средняя",
    ),
    dict(
        id="exp_ew_ru_01", pub="pub_ew_ru_2023",
        materials=["mat_catholyte", "mat_nickel_cathode"], process="proc_electrowinning_ni",
        equipment="eq_ew_cell_diaphragm", facility="fac_smelter_monchegorsk",
        props=["prop_catholyte_flow"],
        attrs={"catholyte_flow_rate_m3_h": 2.5, "current_density_a_m2": 300},
        effect="При скорости циркуляции 2.5 м³/ч на ячейку достигнута стабильная плотность катода без дендритов",
        conclusion="Оптимальная скорость циркуляции католита в диафрагменных ячейках — около 2.5 м³/ч на ячейку.",
        team="team_hydromet", date="2023-01-20", country="RU", confidence="высокая",
        contradicts="concl_ew_intl_01",
    ),
    dict(
        id="exp_ew_intl_01", pub="pub_ew_intl_2022",
        materials=["mat_catholyte", "mat_nickel_cathode"], process="proc_electrowinning_ni",
        equipment="eq_ew_cell_open", facility="fac_smelter_sudbury",
        props=["prop_catholyte_flow"],
        attrs={"catholyte_flow_rate_m3_h": 4.0, "current_density_a_m2": 320},
        effect="Flow rate of 4.0 m3/h per cell minimized concentration polarization in open cells",
        conclusion="В открытых (бездиафрагменных) ячейках оптимальная скорость циркуляции — около 4.0 м³/ч на ячейку.",
        team="team_hydromet", date="2022-05-10", country="INTL", confidence="высокая",
    ),
    dict(
        id="exp_smelt_cu_01", pub="pub_smelt_cu_2023",
        materials=["mat_copper_matte", "mat_slag"], process="proc_smelting_cu",
        equipment="eq_flash_furnace", facility="fac_smelter_monchegorsk",
        props=["prop_au_distribution", "prop_ag_distribution", "prop_pgm_distribution"],
        attrs={"au_distribution_pct": 97.5, "ag_distribution_pct": 92.0, "pgm_distribution_pct": 85.0},
        effect="97.5% Au, 92% Ag и 85% МПГ перешли в медный штейн при стандартной шихте",
        conclusion="При плавке на медный штейн подавляющая часть Au/Ag/МПГ концентрируется в штейне, потери со шлаком минимальны для Au.",
        team="team_pyromet", date="2023-09-01", country="RU", confidence="высокая",
    ),
    dict(
        id="exp_smelt_ni_01", pub="pub_smelt_ni_2022",
        materials=["mat_nickel_matte", "mat_slag"], process="proc_smelting_ni",
        equipment="eq_flash_furnace", facility="fac_smelter_sudbury",
        props=["prop_au_distribution", "prop_pgm_distribution"],
        attrs={"au_distribution_pct": 94.0, "pgm_distribution_pct": 90.0},
        effect="94% Au and 90% PGM reported to nickel matte in flash smelting",
        conclusion="Для никелевого штейна распределение МПГ в штейн выше, чем для медного, за счёт более высокой сульфидной ёмкости.",
        team="team_pyromet", date="2022-02-14", country="INTL", confidence="высокая",
    ),
    dict(
        id="exp_smelt_cu_02", pub="pub_smelt_cu_2021",
        materials=["mat_copper_matte", "mat_slag"], process="proc_smelting_cu",
        equipment="eq_flash_furnace", facility="fac_smelter_monchegorsk",
        props=["prop_ag_distribution"],
        attrs={"ag_distribution_pct": 88.0},
        effect="Снижение содержания серебра в шихте на 15% снизило переход Ag в штейн до 88%",
        conclusion="Извлечение серебра в штейн чувствительно к содержанию Ag в исходной шихте — рекомендован контроль состава сырья.",
        team="team_pyromet", date="2021-05-20", country="RU", confidence="средняя",
    ),
    dict(
        id="exp_heap_cu_01", pub="pub_heap_cu_2021",
        materials=["mat_copper_ore"], process="proc_heap_leaching",
        condition="cond_temperate", equipment="eq_heap_pad", facility="fac_heap_site_ru",
        props=["prop_extraction_rate"],
        attrs={"extraction_rate_pct": 78.0, "leach_days": 120},
        effect="Извлечение меди 78% за 120 суток орошения в умеренном климате",
        conclusion="Кучное выщелачивание медных руд эффективно в умеренном климате при стандартном орошении.",
        team="team_hydromet", date="2021-07-01", country="RU", confidence="средняя",
    ),
    dict(
        id="exp_deep_inj_ru_01", pub="pub_deep_inj_ru_2020",
        materials=["mat_mine_water"], process="proc_deep_injection",
        equipment="eq_deep_well", facility="fac_mine_kuzbass",
        props=["prop_techno_economic"],
        attrs={"capex_musd": 4.2, "opex_musd_year": 0.6, "capacity_m3_day": 1200, "injection_depth_m": 850},
        effect="Закачка 1200 м³/сут на глубину 850 м, капзатраты 4.2 млн $, опекс 0.6 млн $/год",
        conclusion="Закачка в глубокие горизонты в РФ экономически оправдана при производительности от 1000 м³/сут и глубине 700-900 м.",
        team="team_geotech", date="2020-01-15", country="RU", confidence="средняя",
    ),
    dict(
        id="exp_deep_inj_de_01", pub="pub_deep_inj_de_2019",
        materials=["mat_mine_water"], process="proc_deep_injection",
        equipment="eq_deep_well", facility="fac_mine_germany",
        props=["prop_techno_economic"],
        attrs={"capex_musd": 6.8, "opex_musd_year": 0.9, "capacity_m3_day": 2000, "injection_depth_m": 1100},
        effect="Injection of 2000 m3/day at 1100 m depth, capex $6.8M, opex $0.9M/year",
        conclusion="German practice favors deeper injection (1000+ m) with higher capacity and stricter monitoring requirements than typical RU projects.",
        team="team_geotech", date="2019-11-01", country="INTL", confidence="высокая",
    ),
]

# Намеренный пробел (буквально из ТЗ): нет ни одного эксперимента с
# Материал=Никелевая руда, Условие=Холодный климат, Процесс=Кучное выщелачивание.
# mat_nickel_ore и cond_cold заведены в справочники, но НИ ОДИН эксперимент их не связывает.


def build_sample_graph() -> GraphStore:
    gs = GraphStore()

    for mid, name in MATERIALS:
        gs.add_entity(Entity(id=mid, type=EntityType.MATERIAL, name=name))
    for pid, name in PROCESSES:
        gs.add_entity(Entity(id=pid, type=EntityType.PROCESS, name=name))
    for cid, name in CONDITIONS:
        gs.add_entity(Entity(id=cid, type=EntityType.CONDITION, name=name))
    for pid, name in PROPERTIES:
        gs.add_entity(Entity(id=pid, type=EntityType.PROPERTY, name=name))
    for eid, name in EQUIPMENT:
        gs.add_entity(Entity(id=eid, type=EntityType.EQUIPMENT, name=name))
    for fid, name, country in FACILITIES:
        gs.add_entity(Entity(id=fid, type=EntityType.FACILITY, name=name, attrs={"country": country}))
    for tid, name in TEAMS:
        gs.add_entity(Entity(id=tid, type=EntityType.TEAM, name=name))
    for eid, name, team_id in EXPERTS:
        gs.add_entity(Entity(id=eid, type=EntityType.EXPERT, name=name))
        gs.add_relation(Relation(source=eid, target=team_id, type=RelationType.MEMBER_OF))
    for tid, name in TOPICS:
        gs.add_entity(Entity(id=tid, type=EntityType.TOPIC, name=name))

    for pub_id, title, date, country, confidence, topic_ids in PUBLICATIONS:
        gs.add_entity(Entity(
            id=pub_id, type=EntityType.PUBLICATION, name=title,
            attrs={"date": date, "country": country, "confidence": confidence},
        ))
        for topic_id in topic_ids:
            gs.add_relation(Relation(source=pub_id, target=topic_id, type=RelationType.TAGGED_AS))
        for expert_id in AUTHORS.get(pub_id, []):
            gs.add_relation(Relation(source=pub_id, target=expert_id, type=RelationType.AUTHORED_BY))

    conclusion_id_by_exp = {}
    for exp in EXPERIMENTS:
        exp_id = exp["id"]
        attrs = dict(exp["attrs"])
        attrs.update({"date": exp["date"], "country": exp["country"], "confidence": exp["confidence"], "effect": exp["effect"]})
        gs.add_entity(Entity(id=exp_id, type=EntityType.EXPERIMENT, name=f"Эксперимент {exp_id}", attrs=attrs))
        gs.add_relation(Relation(source=exp["pub"], target=exp_id, type=RelationType.DESCRIBES_EXPERIMENT))
        gs.add_relation(Relation(source=exp_id, target=exp["facility"], type=RelationType.AT_FACILITY))
        gs.add_relation(Relation(source=exp_id, target=exp["team"], type=RelationType.CONDUCTED_BY))
        gs.add_relation(Relation(source=exp_id, target=exp["process"], type=RelationType.USES_PROCESS))
        if exp.get("condition"):
            gs.add_relation(Relation(source=exp_id, target=exp["condition"], type=RelationType.AT_CONDITION))
        if exp.get("equipment"):
            gs.add_relation(Relation(source=exp_id, target=exp["equipment"], type=RelationType.ON_EQUIPMENT))
        for mat_id in exp["materials"]:
            gs.add_relation(Relation(source=exp_id, target=mat_id, type=RelationType.USES_MATERIAL))
        for prop_id in exp["props"]:
            gs.add_relation(Relation(source=exp_id, target=prop_id, type=RelationType.MEASURES_PROPERTY, attrs={"effect": exp["effect"]}))

        concl_id = f"concl_{exp_id.replace('exp_', '')}"
        gs.add_entity(Entity(
            id=concl_id, type=EntityType.CONCLUSION, name=exp["conclusion"],
            attrs={"date": exp["date"], "country": exp["country"], "confidence": exp["confidence"], "source": exp["pub"]},
        ))
        gs.add_relation(Relation(source=exp_id, target=concl_id, type=RelationType.PRODUCES_CONCLUSION))
        gs.add_relation(Relation(source=concl_id, target=exp["pub"], type=RelationType.VALIDATED_BY))
        conclusion_id_by_exp[exp_id] = concl_id

    for exp in EXPERIMENTS:
        if exp.get("contradicts"):
            this_concl = conclusion_id_by_exp[exp["id"]]
            other_concl = exp["contradicts"]
            gs.add_relation(Relation(
                source=this_concl, target=other_concl, type=RelationType.CONTRADICTS,
                attrs={"note": "Разные конструкции ячеек (диафрагменная/открытая) дают разную рекомендованную скорость циркуляции — требует уточнения применимости."},
            ))

    return gs


if __name__ == "__main__":
    from pathlib import Path

    gs = build_sample_graph()
    out = Path(__file__).resolve().parent.parent / "data" / "sample_graph.json"
    out.parent.mkdir(exist_ok=True)
    gs.save(out)
    print(f"Saved sample graph to {out} ({gs.g.number_of_nodes()} nodes, {gs.g.number_of_edges()} edges)")
