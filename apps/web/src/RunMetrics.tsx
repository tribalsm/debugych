/** Presentation only: counts belong to the supplied run, never to a selected test. */
export function RunMetrics({passed,failed,errors}:{passed?:number;failed?:number;errors?:number}){
 return <dl className="qa-metrics" aria-label="Измеренные результаты запуска">
  <div className={passed?'metric-passed':''}><dt>Успешно</dt><dd className={passed===undefined?'metric-missing':undefined}>{passed??'Нет данных'}</dd></div>
  <div className={failed?'metric-failed':''}><dt>С отклонением</dt><dd className={failed===undefined?'metric-missing':undefined}>{failed??'Нет данных'}</dd></div>
  <div className={errors?'metric-failed':''}><dt>Ошибки выполнения</dt><dd className={errors===undefined?'metric-missing':undefined}>{errors??'Нет данных'}</dd></div>
 </dl>;
}
