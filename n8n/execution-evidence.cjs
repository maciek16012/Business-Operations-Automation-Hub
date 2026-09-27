const fs = require('fs');
const base = '/usr/local/lib/node_modules/n8n/node_modules/.pnpm';
const packages = fs.readdirSync(base);
const sqlite = require(base + '/' + packages.find(n => n.startsWith('sqlite3@')) + '/node_modules/sqlite3');
const {parse} = require(base + '/' + packages.find(n => n.startsWith('flatted@')) + '/node_modules/flatted');
const db = new sqlite.Database('/home/node/.n8n/database.sqlite', sqlite.OPEN_READONLY);
// Only execution state/output is read. No workflow credentials or user tables are touched.
db.all('SELECT e.id, e.status, e."workflowId", d.data FROM execution_entity e JOIN execution_data d ON d."executionId"=e.id ORDER BY e.id DESC LIMIT 30', [], (error, rows) => {
  if (error) throw error;
  const summary = rows.map(row => {
    const data = parse(row.data).resultData;
    const result = {id:row.id, status:row.status, workflow_id:row.workflowId};
    if (data.error) result.error = data.error.message;
    if (row.workflowId === 'boahEmailErrors2') result.recovery = data.runData?.['Recovery context']?.[0]?.data?.main?.[0]?.[0]?.json;
    return result;
  });
  console.log(JSON.stringify(summary, null, 2)); db.close();
});
