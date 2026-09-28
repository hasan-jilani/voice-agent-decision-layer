// Records race.html for social assets. Renders at 2x via CSS zoom so ffmpeg can
// supersample down; hides controls/lede/method and forces the summary visible so
// the frame is fully used throughout the loop.
const {chromium} = require('playwright');
const css = `html{zoom:2}
   .lede,.method,.controls{display:none!important}
   .result{display:block!important}
   .wrap{padding-block:16px 12px!important;max-width:1100px!important;padding-inline:16px!important}
   .eyebrow{font-size:12px!important;margin-bottom:7px!important;letter-spacing:.12em!important}
   h1{font-size:30px!important;margin-bottom:0!important;letter-spacing:-.022em!important}
   .race{margin-top:14px!important;gap:14px!important}
   .lane-head{padding:14px 16px 0!important}
   .engine .nm{font-size:19px!important} .engine .md{font-size:13px!important}
   .role{font-size:11.5px!important;letter-spacing:.07em!important}
   .stats{padding:14px 16px 13px!important;gap:10px!important}
   .stat .k{font-size:11px!important} .stat .v{font-size:36px!important}
   .stat .sub{font-size:12.5px!important}
   .counted{font-size:12.5px!important;padding:10px 16px!important}
   .stream{height:330px!important}
   .row{padding:10px 16px!important;gap:5px 14px!important}
   .row .act{font-size:14.5px!important}
   .row .say{font-size:13px!important}
   .vd{font-size:11px!important;padding:2px 8px!important}
   .ms{font-size:12.5px!important}
   .pending,.idle{font-size:13px!important;padding:11px 16px!important}
   .verdictbar{font-size:12px!important;padding:12px 16px!important}
   .result{margin-top:13px!important;padding:15px 16px!important}
   .result h2{font-size:15.5px!important;margin-bottom:12px!important}
   .delta .k{font-size:11px!important} .delta .v{font-size:27px!important}
   .delta .n{font-size:12.5px!important}`;
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({viewport:{width:2200,height:1840},
    recordVideo:{dir:'/tmp/vR', size:{width:2200,height:1840}}});
  const p = await ctx.newPage();
  await p.goto('file://' + __dirname + '/race.html');
  await p.addStyleTag({content: css});
  await p.waitForTimeout(9500);
  await ctx.close(); await b.close();
  console.log('recorded to /tmp/vR');
})();
