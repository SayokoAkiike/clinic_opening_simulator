export const DEPARTMENTS = [
  "内科",
  "小児科",
  "皮膚科",
  "整形外科",
  "耳鼻科",
  "歯科",
  "美容系",
] as const;

export type Department = (typeof DEPARTMENTS)[number];

export const WALK_MINUTE_OPTIONS = [
  { value: 5, label: "徒歩5分以内" },
  { value: 10, label: "徒歩10分以内" },
  { value: 15, label: "徒歩15分以内" },
] as const;
