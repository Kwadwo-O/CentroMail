const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');
const source = readFileSync('static/js/mail.js','utf8');
const section = (start,end) => source.slice(source.indexOf(start), source.indexOf(end));
const now = Date.parse('2026-11-17T15:00:00Z');
class Clock extends Date {
    constructor(...args) { super(...(args.length ? args : [now])); }
    static now() { return now; }
}
function control(value='all') {
    return {value,hidden:false,textContent:'',listeners:{},addEventListener(event,listener){this.listeners[event]=listener;},
        setAttribute(key,value){this[key]=value;}};
}
function message(id,time,{sender='Sender',subject='Message',unread=false,starred=false,replyable=true,noreply=false}={}) {
    const classes = new Set(unread?['unread']:[]), stars = new Set(starred?['starred']:[]);
    const checkbox = {checked:true};
    const row = {id,hidden:false,dataset:{messageTime:String(time),canReply:String(replyable),noReply:String(noreply)},
        classList:{contains:value=>classes.has(value),remove:value=>classes.delete(value)},
        contains(element){return element===checkbox;},
        querySelector(selector){return {'.message-check':checkbox,'.star-button':{classList:{contains:value=>stars.has(value)}},
            '.message-sender':{textContent:sender},'.message-subject':{textContent:subject}}[selector];}};
    return row;
}
function inbox(messages,preferences={}) {
    const settings = {'mail-sort':'newest','mail-sort-direction':'desc',...preferences};
    const fields = ['read','star','reply','date'].map(name=>({...control(),id:'mail-filter-'+name}));
    const elements = Object.fromEntries(['#mail-sort','#mail-sort-direction','#clear-mail-filters','#mail-filter-count',
        '#mail-filter-status','#mail-page-count','#empty-state','.mail-selection-actions','#mail-selection-count'].map(name=>[name,control()]));
    const icon=control(),label=control();elements['#mail-sort-direction'].querySelector=selector=>selector==='.m3e-icon'?icon:label;
    const listeners={};
    const list={children:messages,contains:()=>false,querySelector:()=>null,focus(){context.document.activeElement=this;},
        insertBefore(row,before){messages.splice(messages.indexOf(row),1);messages.splice(before?messages.indexOf(before):messages.length,0,row);}};
    const context={Date:Clock,focusedIndex:-1,hasMore:true,loadedTotal:100,actionPending:false,list,
        rows:()=>messages,visibleRows:()=>messages.filter(row=>!row.hidden),search:{value:''},selectAll:{},
        document:{activeElement:{},querySelector:selector=>elements[selector],
            querySelectorAll:selector=>selector==='.mail-filter-fields select'?fields:[],
            addEventListener(event,listener){listeners[event]=listener;}},
        window:{CentroMailAppearance:{get:key=>settings[key],set(key,value){settings[key]=value;listeners['centromail-appearance-change']();}}}};
    vm.runInNewContext(section('const sort =','const showFeedback =')+section('const updateSelection =','const setRefreshBusy =')+
        'this.syncSort=syncSort;this.sortMessages=sortMessages;this.applyFilters=applyFilters;this.selected=selected;',context);
    context.syncSort();
    return {context,settings,fields,elements,icon,label,messages,
        filter(key,value){const field=fields.find(item=>item.id==='mail-filter-'+key);field.value=value;field.listeners.change();},
        ids:()=>messages.filter(row=>!row.hidden).map(row=>row.id)};
}

test('default date order stays newest first across reply types and additional pages, and direction reverses it',()=>{
    const view=inbox([message('old',100,{replyable:true}),message('new',300,{replyable:false,noreply:true}),message('middle',200)]);
    assert.deepEqual(view.ids(),['new','middle','old']);
    view.messages.push(message('newer',400));view.context.sortMessages();
    assert.deepEqual(view.ids(),['newer','new','middle','old']);
    view.elements['#mail-sort-direction'].listeners.click();
    assert.deepEqual(view.ids(),['old','middle','new','newer']);
    assert.equal(view.label.textContent,'Oldest first');
    assert.match(view.elements['#mail-sort-direction']['aria-label'],/Switch to newest first/);
});

test('sender and subject ordering ignores case and keeps newest first within matching names',()=>{
    const view=inbox([message('a',100,{sender:'alice',subject:'Update 10'}),message('b',300,{sender:'ALICE',subject:'Update 2'}),
        message('c',200,{sender:'Bob',subject:'Alert'})],{'mail-sort':'sender','mail-sort-direction':'asc'});
    assert.deepEqual(view.ids(),['b','a','c']);
    view.elements['#mail-sort'].value='subject';view.elements['#mail-sort'].listeners.change();
    assert.deepEqual(view.ids(),['c','b','a']);
    view.elements['#mail-sort-direction'].listeners.click();
    assert.deepEqual(view.ids(),['a','b','c']);
});

test('combined read, star and reply filters exclude hidden selections and clear without deleting messages',()=>{
    const view=inbox([message('new',now-60000,{unread:true,starred:true}),message('old',now-100000,{unread:true,replyable:false,noreply:true}),
        message('read',now-200000,{starred:true,replyable:false,noreply:true})]);
    view.filter('read','unread');assert.deepEqual(view.ids(),['new','old']);
    assert.deepEqual(Array.from(view.context.selected(),row=>row.id),['new','old']);
    assert.equal(view.messages.find(row=>row.id==='read').querySelector('.message-check').checked,false);
    view.filter('star','starred');assert.deepEqual(view.ids(),['new']);
    view.filter('reply','noreply');assert.deepEqual(view.ids(),[]);
    assert.equal(view.context.selectAll.disabled,true);
    assert.equal(view.elements['#empty-state'].hidden,false);
    view.elements['#clear-mail-filters'].listeners.click();
    assert.equal(view.ids().length,3);assert.equal(view.messages.length,3);
    assert.equal(view.elements['#mail-filter-count'].hidden,true);
});

test('date filters include the local calendar boundary and newly loaded messages use the active filter',()=>{
    const midnight=new Clock();midnight.setHours(0,0,0,0);
    const view=inbox([message('today',midnight.getTime()),message('yesterday',midnight.getTime()-1),
        message('week',midnight.getTime()-6*86400000),message('older',midnight.getTime()-31*86400000)]);
    view.filter('date','today');assert.deepEqual(view.ids(),['today']);
    view.filter('date','7');assert.deepEqual(view.ids(),['today','yesterday','week']);
    view.messages.push(message('incoming',now-1000));view.context.sortMessages();view.context.applyFilters();
    assert.deepEqual(view.ids(),['incoming','today','yesterday','week']);
    view.filter('date','30');assert.equal(view.ids().includes('older'),false);
});
