import { ExternalLink, MapPin, Users, Calendar, FlaskConical, CheckCircle2, Clock } from "lucide-react";

export default function SourceCard({ type, data, index }) {
  if (type === "publication") return <PublicationCard data={data} index={index} />;
  return <TrialCard data={data} index={index} />;
}

function PublicationCard({ data, index }) {
  return (
    <div className="bg-cura-900/30 border border-cura-800/40 rounded-xl p-3 hover:border-cura-700/60 transition-all group">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 mb-1">
            <span className="text-[10px] font-medium text-cura-600 bg-cura-800/50 px-1.5 py-0.5 rounded">
              [{index}]
            </span>
            <span className="text-[10px] text-cura-600">
              {data.source}
            </span>
            {data.year && (
              <span className="flex items-center gap-0.5 text-[10px] text-cura-600">
                <Calendar className="w-2.5 h-2.5" />
                {data.year}
              </span>
            )}
          </div>
          <h5 className="text-xs font-medium text-cura-200 leading-snug line-clamp-2">
            {data.title}
          </h5>
          {data.authors?.length > 0 && (
            <p className="text-[11px] text-cura-600 mt-1 truncate">
              {data.authors.slice(0, 3).join(", ")}
              {data.authors.length > 3 && ` +${data.authors.length - 3} more`}
            </p>
          )}
          {data.abstract && (
            <p className="text-[11px] text-cura-500 mt-1.5 line-clamp-2 leading-relaxed">
              {data.abstract}
            </p>
          )}
        </div>
        {data.url && (
          <a
            href={data.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex-shrink-0 w-7 h-7 flex items-center justify-center rounded-lg bg-cura-800/40 text-cura-500 hover:bg-cura-700 hover:text-cura-200 transition-all opacity-60 group-hover:opacity-100"
          >
            <ExternalLink className="w-3 h-3" />
          </a>
        )}
      </div>
    </div>
  );
}

function TrialCard({ data, index }) {
  const statusColors = {
    RECRUITING: "text-green-400 bg-green-950/50",
    COMPLETED: "text-blue-400 bg-blue-950/50",
    ACTIVE_NOT_RECRUITING: "text-amber-400 bg-amber-950/50",
  };
  const statusClass = statusColors[data.status] || "text-cura-400 bg-cura-800/50";

  return (
    <div className="bg-cura-900/30 border border-cura-800/40 rounded-xl p-3 hover:border-cura-700/60 transition-all group">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 mb-1 flex-wrap">
            <span className="text-[10px] font-medium text-cura-600 bg-cura-800/50 px-1.5 py-0.5 rounded">
              [T{index}]
            </span>
            {data.nct_id && (
              <span className="text-[10px] text-cura-600 font-mono">
                {data.nct_id}
              </span>
            )}
            {data.status && (
              <span
                className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${statusClass}`}
              >
                {data.status === "RECRUITING" && (
                  <Clock className="w-2.5 h-2.5 inline mr-0.5 -mt-px" />
                )}
                {data.status === "COMPLETED" && (
                  <CheckCircle2 className="w-2.5 h-2.5 inline mr-0.5 -mt-px" />
                )}
                {data.status.replace(/_/g, " ")}
              </span>
            )}
          </div>
          <h5 className="text-xs font-medium text-cura-200 leading-snug line-clamp-2">
            {data.title}
          </h5>

          {/* Interventions */}
          {data.interventions?.length > 0 && (
            <div className="flex items-center gap-1 mt-1.5 flex-wrap">
              <FlaskConical className="w-2.5 h-2.5 text-cura-600 flex-shrink-0" />
              {data.interventions.slice(0, 3).map((interv, i) => (
                <span
                  key={i}
                  className="text-[10px] text-cura-400 bg-cura-800/30 px-1.5 py-0.5 rounded"
                >
                  {interv}
                </span>
              ))}
            </div>
          )}

          {/* Locations */}
          {data.locations?.length > 0 && (
            <p className="flex items-center gap-1 text-[11px] text-cura-600 mt-1.5">
              <MapPin className="w-2.5 h-2.5 flex-shrink-0" />
              <span className="truncate">
                {data.locations.slice(0, 2).join(" · ")}
              </span>
            </p>
          )}

          {/* Contacts */}
          {data.contacts?.length > 0 && (
            <p className="flex items-center gap-1 text-[11px] text-cura-600 mt-1">
              <Users className="w-2.5 h-2.5 flex-shrink-0" />
              {data.contacts[0]}
            </p>
          )}

          {/* Eligibility snippet */}
          {data.eligibility && (
            <p className="text-[10px] text-cura-600 mt-1.5 line-clamp-2 leading-relaxed">
              {data.eligibility}
            </p>
          )}
        </div>
        {data.url && (
          <a
            href={data.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex-shrink-0 w-7 h-7 flex items-center justify-center rounded-lg bg-cura-800/40 text-cura-500 hover:bg-cura-700 hover:text-cura-200 transition-all opacity-60 group-hover:opacity-100"
          >
            <ExternalLink className="w-3 h-3" />
          </a>
        )}
      </div>
    </div>
  );
}
