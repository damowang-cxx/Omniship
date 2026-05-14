import Link from "next/link";
import { RefreshCw, Search, UploadCloud } from "lucide-react";
import styles from "./AirWaybillsToolbar.module.css";

export function AirWaybillsToolbar({
  query,
  isScraping,
  onFullRefresh,
  onQueryChange,
  onScrape,
  canUpdate = true
}: {
  query: string;
  isScraping: boolean;
  onFullRefresh: () => void;
  onQueryChange: (value: string) => void;
  onScrape: () => void;
  canUpdate?: boolean;
}) {
  return (
    <div className={styles.toolbar}>
      <label className={styles.searchBox}>
        <Search aria-hidden="true" size={18} />
        <input
          aria-label="搜索 Number"
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="搜索 Number，例如 784-84063276 或 78484063276"
          value={query}
        />
      </label>
      <div className={styles.actions}>
        <Link className={styles.secondaryButton} href="/waybill-uploads">
          <UploadCloud aria-hidden="true" size={17} />
          Upload Pre Alert
        </Link>
        {canUpdate && (
          <>
            <button
              className={styles.secondaryButton}
              disabled={isScraping}
              onClick={onFullRefresh}
              type="button"
            >
              全量更新
            </button>
            <button
              className={styles.scrapeButton}
              disabled={isScraping}
              onClick={onScrape}
              type="button"
            >
              <RefreshCw
                aria-hidden="true"
                className={isScraping ? styles.spin : ""}
                size={17}
              />
              {isScraping ? "更新中" : "立即更新"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
