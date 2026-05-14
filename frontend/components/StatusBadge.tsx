import styles from "./StatusBadge.module.css";

export function StatusBadge({ value }: { value?: string | null }) {
  const normalized = value?.toLowerCase() ?? "unknown";

  return (
    <span className={styles.badge} data-status={normalized}>
      {value || "-"}
    </span>
  );
}

