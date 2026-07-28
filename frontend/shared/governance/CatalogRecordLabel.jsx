/**
 * Primary catalog label: short title + small id underneath.
 */
export function CatalogRecordLabel({ title, id, titleAttr, meta }) {
  const tip = titleAttr || id || undefined;
  return (
    <div className="catalog-record" title={tip}>
      <strong className="catalog-record__title">{title || "—"}</strong>
      {id || meta ? (
        <small className="catalog-record__id">
          {id ? <span className="catalog-record__id-text">{id}</span> : null}
          {id && meta ? <span className="catalog-record__sep"> · </span> : null}
          {meta ? <span>{meta}</span> : null}
        </small>
      ) : null}
    </div>
  );
}
