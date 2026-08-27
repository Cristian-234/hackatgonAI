from __future__ import annotations

import argparse
import csv
import math
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "KNOWLEDGE_NEXUS_LATAM_DATA_V1_RC2_PARTICIPANTS"

STOPWORDS = {
    "a", "al", "ante", "bajo", "con", "contra", "como", "de", "del", "desde",
    "durante", "e", "el", "ella", "en", "entre", "es", "esta", "este", "estos",
    "hacia", "la", "las", "lo", "los", "mediante", "o", "para", "por", "que",
    "se", "sin", "sobre", "su", "sus", "un", "una", "unas", "unos", "y",
    "institucion", "institucional", "requiere", "fortalecer", "capacidad",
    "capacidades", "abordar", "aprovechamiento", "articulado", "informacion",
    "conocimiento", "previo", "existentes", "problema", "problemas",
    "contexto", "aplicado", "aplicada", "relacion", "relacionado", "relacionada",
    "relacionadas", "relacionados",
}

SYNONYMS = {
    "desercion": {"permanencia", "attrition", "abandono", "riesgo", "trayectorias"},
    "permanencia": {"desercion", "attrition", "riesgo", "trayectorias", "educacion"},
    "attrition": {"desercion", "permanencia", "riesgo"},
    "estudiantil": {"educacion", "educativa", "educativas", "academico"},
    "educativas": {"educacion", "aprendizaje", "formacion"},
    "educativa": {"educacion", "aprendizaje", "formacion"},
    "aprendizaje": {"educativa", "educacion", "formacion", "curriculo"},
    "competencias": {"evaluacion", "aprendizaje", "evidencias"},
    "cardiovascular": {"ecg", "wearables", "salud", "monitoreo"},
    "agua": {"ambiente", "calidad", "territorio"},
    "finanzas": {"financiera", "riesgo", "mercados"},
    "curriculo": {"asignatura", "competencia", "aprendizaje", "formacion"},
}


@dataclass
class Entity:
    id: str
    type: str
    title: str
    text: str
    source_file: str
    fields: dict[str, str]
    relations: dict[str, str]


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text).lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text


def tokens(text: str, expand: bool = True) -> list[str]:
    base = [
        t for t in re.findall(r"[a-z0-9]+", normalize(text))
        if len(t) > 2 and t not in STOPWORDS
    ]
    if not expand:
        return base
    expanded = list(base)
    for token in base:
        expanded.extend(SYNONYMS.get(token, ()))
    return expanded


def read_csv(relative: str) -> list[dict[str, str]]:
    path = DATA_ROOT / relative
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def join_fields(row: dict[str, str], names: Iterable[str]) -> str:
    return " ".join(str(row.get(name, "") or "") for name in names)


def load_entities() -> tuple[list[Entity], dict[str, Entity]]:
    entities: list[Entity] = []

    specs = [
        (
            "03_knowledge_needs/institutional_needs.csv",
            "need_id",
            "need",
            "title",
            ["title", "description", "context", "expected_impact", "priority"],
            ["originating_unit", "priority", "status"],
        ),
        (
            "03_knowledge_needs/projects.csv",
            "project_id",
            "project",
            "title",
            ["title", "problem_statement", "abstract", "general_objective", "methodology", "expected_results", "application_context", "keywords", "disciplinary_area"],
            ["faculty_id", "program_id", "group_id"],
        ),
        (
            "03_knowledge_needs/theses.csv",
            "thesis_id",
            "thesis",
            "title",
            ["title", "abstract", "problem_statement", "general_objective", "methodology", "main_results", "conclusions", "keywords", "research_area", "application_context", "data_or_population"],
            ["program_id"],
        ),
        (
            "03_knowledge_needs/publications.csv",
            "publication_id",
            "publication",
            "title",
            ["title", "abstract", "keywords", "publication_type", "journal_or_event"],
            ["related_project_id"],
        ),
        (
            "01_institution/institutional_capabilities.csv",
            "capability_id",
            "capability",
            "capability_name",
            ["capability_name", "capability_type", "description", "available_resources", "application_domains", "maturity_level"],
            ["responsible_unit"],
        ),
        (
            "02_people_curriculum/researchers.csv",
            "researcher_id",
            "researcher",
            "full_name",
            ["full_name", "academic_background", "profile_summary", "research_interests", "methodological_expertise", "application_domains"],
            ["faculty_id", "primary_program_id"],
        ),
        (
            "02_people_curriculum/subjects.csv",
            "subject_id",
            "subject",
            "subject_name",
            ["subject_name", "description", "purpose", "main_topics", "disciplinary_area"],
            ["program_id"],
        ),
    ]

    for source_file, id_col, entity_type, title_col, text_cols, relation_cols in specs:
        for row in read_csv(source_file):
            entity_id = row[id_col]
            fields = {col: str(row.get(col, "") or "") for col in text_cols}
            relations = {col: str(row.get(col, "") or "") for col in relation_cols}
            entities.append(
                Entity(
                    id=entity_id,
                    type=entity_type,
                    title=str(row.get(title_col, "") or entity_id),
                    text=join_fields(row, text_cols),
                    source_file=source_file,
                    fields=fields,
                    relations=relations,
                )
            )

    by_id = {entity.id: entity for entity in entities}
    return entities, by_id


def build_tfidf(entities: list[Entity]) -> tuple[dict[str, Counter], dict[str, float]]:
    term_counts: dict[str, Counter] = {}
    document_frequency: Counter = Counter()
    for entity in entities:
        counts = Counter(tokens(entity.text))
        term_counts[entity.id] = counts
        document_frequency.update(counts.keys())

    total_docs = len(entities)
    idf = {
        term: math.log((1 + total_docs) / (1 + frequency)) + 1
        for term, frequency in document_frequency.items()
    }
    return term_counts, idf


def vectorize(counts: Counter, idf: dict[str, float]) -> dict[str, float]:
    return {term: count * idf.get(term, 0.0) for term, count in counts.items()}


def cosine(left: dict[str, float], right: dict[str, float]) -> float:
    common = set(left) & set(right)
    numerator = sum(left[t] * right[t] for t in common)
    left_norm = math.sqrt(sum(v * v for v in left.values()))
    right_norm = math.sqrt(sum(v * v for v in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def field_evidence(source: Entity, target: Entity, max_items: int = 4) -> list[dict[str, str]]:
    source_terms = set(tokens(source.text, expand=False))
    target_terms = set(tokens(target.text, expand=False))
    shared = source_terms & target_terms
    evidence = []
    for field, value in target.fields.items():
        field_terms = set(tokens(value, expand=False))
        hits = sorted((field_terms & shared), key=lambda item: (-len(item), item))
        if hits:
            evidence.append(
                {
                    "source": f"Data V1.0 / {target.source_file} / {target.id} / {field}",
                    "matched_terms": ", ".join(hits[:6]),
                    "fragment": str(value)[:260],
                }
            )
        if len(evidence) >= max_items:
            break
    if evidence:
        return evidence

    expanded_shared = set(tokens(source.text)) & set(tokens(target.text))
    for field, value in target.fields.items():
        field_terms = set(tokens(value))
        hits = sorted((field_terms & expanded_shared), key=lambda item: (-len(item), item))
        if hits:
            evidence.append(
                {
                    "source": f"Data V1.0 / {target.source_file} / {target.id} / {field}",
                    "matched_terms": "senales relacionadas: " + ", ".join(hits[:6]),
                    "fragment": str(value)[:260],
                }
            )
        if len(evidence) >= max_items:
            break
    return evidence


def relation_type(source: Entity, target: Entity) -> str:
    if source.type == "need" and target.type == "project":
        return "antecedente o experiencia institucional relevante"
    if source.type == "need" and target.type == "thesis":
        return "antecedente para trabajo de grado o investigacion"
    if source.type == "need" and target.type == "researcher":
        return "posible experto o colaborador"
    if source.type == "need" and target.type == "capability":
        return "capacidad institucional activable"
    if source.type == "need" and target.type == "subject":
        return "articulacion curricular potencial"
    if target.type == "publication":
        return "evidencia de produccion investigativa"
    return "conexion semantica relevante"


def opportunity_for(source: Entity, target: Entity) -> str:
    if target.type == "project":
        return f"Usar {target.id} como antecedente para formular una iniciativa asociada a '{source.title}'."
    if target.type == "thesis":
        return f"Reutilizar hallazgos de {target.id} como base para nuevos trabajos de grado sobre '{source.title}'."
    if target.type == "researcher":
        return f"Invitar a {target.title} como experto para evaluar o codisenar una respuesta a la necesidad."
    if target.type == "capability":
        return f"Activar la capacidad {target.title} para prototipar una solucion institucional."
    if target.type == "subject":
        return f"Conectar la necesidad con la asignatura {target.title} para proyectos de aula o actualizacion curricular."
    if target.type == "publication":
        return f"Usar la publicacion {target.id} como evidencia academica para sustentar la oportunidad."
    return "Explorar esta conexion como oportunidad institucional."


def score_entities(source: Entity, entities: list[Entity], top_k: int, balanced: bool) -> list[dict]:
    term_counts, idf = build_tfidf(entities)
    vectors = {entity.id: vectorize(term_counts[entity.id], idf) for entity in entities}
    source_vector = vectors[source.id]

    results = []
    for target in entities:
        if target.id == source.id or target.type == "need":
            continue
        base_score = cosine(source_vector, vectors[target.id])
        source_terms = set(tokens(source.text, expand=False))
        target_terms = set(tokens(target.text, expand=False))
        shared_terms = source_terms & target_terms
        expanded_shared = set(tokens(source.text)) & set(tokens(target.text))
        literal_bonus = min(len(shared_terms) / 10, 1.0)
        score = min((base_score * 0.86) + (literal_bonus * 0.14), 1.0)
        if score <= 0:
            continue
        evidence = field_evidence(source, target)
        if not evidence:
            continue
        results.append(
            {
                "id": target.id,
                "type": target.type,
                "title": target.title,
                "relation": relation_type(source, target),
                "score": round(score, 4),
                "priority": "HIGH" if score >= 0.36 else "MEDIUM" if score >= 0.22 else "LOW",
                "why": (
                    f"Coincidencias directas: {', '.join(sorted(shared_terms)[:8]) or 'sin coincidencia literal fuerte'}. "
                    f"Senales semanticas: {', '.join(sorted(expanded_shared)[:8])}."
                ),
                "evidence": evidence,
                "opportunity": opportunity_for(source, target),
            }
        )

    ranked = sorted(results, key=lambda item: item["score"], reverse=True)
    if not balanced:
        return ranked[:top_k]

    type_order = ["project", "thesis", "researcher", "capability", "subject", "publication"]
    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in ranked:
        grouped[item["type"]].append(item)

    selected = []
    for entity_type in type_order:
        selected.extend(grouped.get(entity_type, [])[:2])

    seen = {item["id"] for item in selected}
    for item in ranked:
        if len(selected) >= top_k:
            break
        if item["id"] not in seen:
            selected.append(item)
            seen.add(item["id"])

    return selected[:top_k]


def entity_summary(entity: Entity) -> dict[str, str]:
    return {
        "id": entity.id,
        "type": entity.type,
        "title": entity.title,
        "source_file": entity.source_file,
        "text": entity.text[:500],
        "relations": entity.relations,
    }


def available_needs() -> list[dict[str, str]]:
    entities, _ = load_entities()
    return [
        {
            "id": entity.id,
            "title": entity.title,
            "priority": entity.relations.get("priority", ""),
            "status": entity.relations.get("status", ""),
            "source_file": entity.source_file,
        }
        for entity in entities
        if entity.type == "need"
    ]


def add_node(nodes: dict[str, dict], entity: Entity, inferred_score: float | None = None) -> None:
    existing = nodes.get(entity.id, {})
    nodes[entity.id] = {
        "id": entity.id,
        "type": entity.type,
        "title": entity.title,
        "source_file": entity.source_file,
        "score": inferred_score if inferred_score is not None else existing.get("score"),
    }


def add_edge(
    edges: list[dict],
    source: str,
    target: str,
    relation: str,
    kind: str,
    evidence: str,
    score: float | None = None,
) -> None:
    edge_id = f"{source}->{target}:{relation}:{kind}"
    if any(edge["id"] == edge_id for edge in edges):
        return
    edges.append(
        {
            "id": edge_id,
            "source": source,
            "target": target,
            "relation": relation,
            "kind": kind,
            "evidence": evidence,
            "score": score,
        }
    )


def load_structural_entities() -> dict[str, Entity]:
    entities: list[Entity] = []
    specs = [
        (
            "01_institution/faculties.csv",
            "faculty_id",
            "faculty",
            "faculty_name",
            ["faculty_name", "description", "strategic_focus"],
            [],
        ),
        (
            "01_institution/programs.csv",
            "program_id",
            "program",
            "program_name",
            ["program_name", "description", "disciplinary_area", "graduate_profile", "strategic_topics"],
            ["faculty_id"],
        ),
        (
            "01_institution/research_groups.csv",
            "group_id",
            "group",
            "group_name",
            ["group_name", "description", "mission", "main_area", "interdisciplinary"],
            ["faculty_id"],
        ),
        (
            "01_institution/research_lines.csv",
            "line_id",
            "line",
            "line_name",
            ["line_name", "description", "keywords"],
            ["group_id"],
        ),
    ]
    for source_file, id_col, entity_type, title_col, text_cols, relation_cols in specs:
        for row in read_csv(source_file):
            entity_id = row[id_col]
            entities.append(
                Entity(
                    id=entity_id,
                    type=entity_type,
                    title=str(row.get(title_col, "") or entity_id),
                    text=join_fields(row, text_cols),
                    source_file=source_file,
                    fields={col: str(row.get(col, "") or "") for col in text_cols},
                    relations={col: str(row.get(col, "") or "") for col in relation_cols},
                )
            )
    return {entity.id: entity for entity in entities}


def build_graph(source: Entity, results: list[dict], by_id: dict[str, Entity]) -> dict:
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    structural = load_structural_entities()
    all_entities = {**structural, **by_id}

    add_node(nodes, source)
    selected_ids = {item["id"] for item in results}

    for item in results:
        target = by_id[item["id"]]
        add_node(nodes, target, inferred_score=item["score"])
        add_edge(
            edges,
            source.id,
            target.id,
            item["relation"],
            "inferred",
            item["evidence"][0]["source"] if item.get("evidence") else target.source_file,
            item["score"],
        )

    for row in read_csv("03_knowledge_needs/researcher_project.csv"):
        researcher_id = row["researcher_id"]
        project_id = row["project_id"]
        if project_id in selected_ids or researcher_id in selected_ids:
            for entity_id in [researcher_id, project_id]:
                if entity_id in all_entities:
                    add_node(nodes, all_entities[entity_id])
            add_edge(
                edges,
                researcher_id,
                project_id,
                f"participa como {row['role']}",
                "explicit",
                f"Data V1.0 / 03_knowledge_needs/researcher_project.csv / {researcher_id}-{project_id} / role",
            )

    for row in read_csv("03_knowledge_needs/project_group.csv"):
        project_id = row["project_id"]
        group_id = row["group_id"]
        if project_id in selected_ids:
            for entity_id in [project_id, group_id]:
                if entity_id in all_entities:
                    add_node(nodes, all_entities[entity_id])
            add_edge(
                edges,
                project_id,
                group_id,
                row["relation"],
                "explicit",
                f"Data V1.0 / 03_knowledge_needs/project_group.csv / {project_id}-{group_id} / relation",
            )

    for row in read_csv("03_knowledge_needs/publication_project.csv"):
        publication_id = row["publication_id"]
        project_id = row["project_id"]
        if publication_id in selected_ids or project_id in selected_ids:
            for entity_id in [publication_id, project_id]:
                if entity_id in all_entities:
                    add_node(nodes, all_entities[entity_id])
            add_edge(
                edges,
                publication_id,
                project_id,
                row["relation"],
                "explicit",
                f"Data V1.0 / 03_knowledge_needs/publication_project.csv / {publication_id}-{project_id} / relation",
            )

    for row in read_csv("03_knowledge_needs/publication_researcher.csv"):
        publication_id = row["publication_id"]
        researcher_id = row["researcher_id"]
        if publication_id in selected_ids or researcher_id in selected_ids:
            for entity_id in [publication_id, researcher_id]:
                if entity_id in all_entities:
                    add_node(nodes, all_entities[entity_id])
            add_edge(
                edges,
                researcher_id,
                publication_id,
                f"publica como {row['role']}",
                "explicit",
                f"Data V1.0 / 03_knowledge_needs/publication_researcher.csv / {publication_id}-{researcher_id} / role",
            )

    for row in read_csv("03_knowledge_needs/thesis_advisor.csv"):
        thesis_id = row["thesis_id"]
        researcher_id = row["researcher_id"]
        if thesis_id in selected_ids or researcher_id in selected_ids:
            for entity_id in [thesis_id, researcher_id]:
                if entity_id in all_entities:
                    add_node(nodes, all_entities[entity_id])
            add_edge(
                edges,
                researcher_id,
                thesis_id,
                f"asesora como {row['role']}",
                "explicit",
                f"Data V1.0 / 03_knowledge_needs/thesis_advisor.csv / {thesis_id}-{researcher_id} / role",
            )

    for node in list(nodes.values()):
        entity = all_entities.get(node["id"])
        if not entity:
            continue
        program_id = entity.relations.get("program_id") or entity.relations.get("primary_program_id")
        faculty_id = entity.relations.get("faculty_id")
        group_id = entity.relations.get("group_id")
        if program_id and program_id in all_entities:
            add_node(nodes, all_entities[program_id])
            add_edge(edges, node["id"], program_id, "pertenece al programa", "explicit", f"Data V1.0 / {entity.source_file} / {entity.id} / program_id")
        if faculty_id and faculty_id in all_entities:
            add_node(nodes, all_entities[faculty_id])
            add_edge(edges, node["id"], faculty_id, "pertenece a facultad", "explicit", f"Data V1.0 / {entity.source_file} / {entity.id} / faculty_id")
        if group_id and group_id in all_entities:
            add_node(nodes, all_entities[group_id])
            add_edge(edges, node["id"], group_id, "vinculado a grupo", "explicit", f"Data V1.0 / {entity.source_file} / {entity.id} / group_id")

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "summary": {
            "nodes": len(nodes),
            "edges": len(edges),
            "explicit_edges": sum(1 for edge in edges if edge["kind"] == "explicit"),
            "inferred_edges": sum(1 for edge in edges if edge["kind"] == "inferred"),
        },
    }


def connect_need(need_id: str, top_k: int = 12, balanced: bool = True) -> dict:
    entities, by_id = load_entities()
    if need_id not in by_id:
        raise ValueError(f"No existe la entidad {need_id}")
    source = by_id[need_id]
    if source.type != "need":
        raise ValueError(f"{need_id} no es una necesidad institucional")

    results = score_entities(source, entities, top_k, balanced=balanced)
    coverage = {
        entity_type: sum(1 for item in results if item["type"] == entity_type)
        for entity_type in ["project", "thesis", "researcher", "capability", "subject", "publication"]
    }
    evidence_count = sum(len(item.get("evidence", [])) for item in results)
    graph = build_graph(source, results, by_id)
    return {
        "source": entity_summary(source),
        "results": results,
        "graph": graph,
        "metrics": {
            "entities_processed": len(entities),
            "connections_returned": len(results),
            "evidence_items": evidence_count,
            "coverage_by_type": coverage,
            "graph_nodes": graph["summary"]["nodes"],
            "graph_edges": graph["summary"]["edges"],
            "explicit_edges": graph["summary"]["explicit_edges"],
            "inferred_edges": graph["summary"]["inferred_edges"],
            "mode": "balanced" if balanced else "global_ranking",
        },
    }


def print_results(source: Entity, results: list[dict]) -> None:
    print(f"Origen: {source.id} | {source.title}")
    print(f"Fuente: Data V1.0 / {source.source_file}")
    print()
    for index, item in enumerate(results, start=1):
        print(f"{index}. {item['id']} [{item['type']}] - {item['title']}")
        print(f"   Relacion: {item['relation']}")
        print(f"   Prioridad: {item['priority']} | Score: {item['score']}")
        print(f"   Por que: {item['why']}")
        print(f"   Oportunidad: {item['opportunity']}")
        print("   Evidencia:")
        for ev in item["evidence"][:3]:
            print(f"   - {ev['source']}")
            print(f"     Terminos: {ev['matched_terms']}")
            print(f"     Fragmento: {ev['fragment']}")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Knowledge Nexus LATAM MVP")
    parser.add_argument("--need", default="NEED-001", help="ID de necesidad institucional")
    parser.add_argument("--top", type=int, default=12, help="Numero de conexiones a mostrar")
    parser.add_argument("--ranking-only", action="store_true", help="Mostrar solo ranking global por score")
    args = parser.parse_args()

    entities, by_id = load_entities()
    if args.need not in by_id:
        available = ", ".join(sorted(e.id for e in entities if e.type == "need")[:10])
        raise SystemExit(f"No existe {args.need}. Ejemplos disponibles: {available}")
    source = by_id[args.need]
    if source.type != "need":
        raise SystemExit("--need debe apuntar a una entidad tipo necesidad institucional.")

    results = score_entities(source, entities, args.top, balanced=not args.ranking_only)
    print_results(source, results)


if __name__ == "__main__":
    main()
