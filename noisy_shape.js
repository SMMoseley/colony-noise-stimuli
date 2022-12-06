#!/usr/bin/env node
const os = require("os");
const _ = require("underscore");
const t = require("../lib/client");           // bank of apparatus manipulation functions
const logger = require("../lib/log");
const util = require("../lib/util");

const name = "shape";
const version = require('../package.json').version;

const argv = require("yargs")
    .usage("Shape subject for GNG or 2AC task.\nUsage: $0 [options] subject_id @slack-id")
//    .describe("F", "skip immediately to holding pattern(block 4)")
    .describe("B", "skip immediately to specific block (0-4)")
    .describe("color", "set cue color: red, green, blue")
    .describe("position","set cue position: left, center, right")
    .describe("no-notify", "if set, don't an email when the bird completes block 4")
    .describe("trials", "set the number of trials per block in blocks 2-3")
    .describe("feed-delay", "time (in ms) to wait between response and feeding")
    .describe("feed-duration", "time (in ms) to run feed motor")
    .default({color: "blue", position: "left", trials: 100, "feed-delay": 0, "B": 0, "feed-duration": 500})
    .boolean(['F'])
    .demand(2)
    .argv;

const par = {
    subject: util.check_subject(argv._[0]), // sets the subject number
    user: argv._[1],
    active: true,
    block_trials: argv.trials,  // number of trials in blocks 2+
    cue_position: argv.position,
    cue_color: argv.color,
    feed_duration: argv["feed-duration"],
    feed_delay: argv["feed-delay"],
    feeders: ["feeder_motor"],
    blink_period: 5000,
};

const state = {
    trial: 0,                   // trial number
    block: -1,                   // shape paradigm block
    phase: null,                 // trial phase
    paused: false                               //pause trials
}

const meta = {
    type: "experiment",
    variables: {
        trial: "integer",
        block: [0, 1, 2],
        phase: "string",
        paused: [true, false]
    }
}

let sock;
const update_state = t.state_changer(name, state);

let start;
/*if (argv.F || argv.B == 4)
    start = block4_peck1;
else*/ if (argv.B == 0)
    start = block0_await;
else if (argv.B == 1)
    start = block1_await;
else if (argv.B == 2)
    start = block2_await;
/*else if (argv.B == 3)
    start = block3_peck1;*/
else {
    logger.error("invalid starting block number (choose 0-2)");
    process.exit(-1);
}

t.connect(name, function(socket) {

    sock = socket;

    // these REQ messages require a response!
    sock.on("get-state", function(data, rep) {
        logger.debug("req to shape: get-state");
        if (rep) rep("ok", state);
    });
    sock.on("get-params", function(data, rep) {
        logger.debug("req to shape: get-params");
        if (rep) rep("ok", par);
    });
    sock.on("get-meta", function(data, rep) {
        logger.debug("req to shape: get-meta");
        if (rep) rep("ok", meta);
    });
    sock.on("change-state", function(data, rep) {
        logger.debug("req to %s: change-state", name, data);
        if (data.paused !== undefined) {
            state.paused = data.paused;
            t.state_changed(name,state);
        }
        if (rep) rep("ok");
    });
    sock.on("reset-state", function(data, rep) { rep("ok") });
    sock.on("state-changed", function(data) { logger.debug("pub to %s: state-changed", name, data)})

    // update user and subject information:
    t.change_state("experiment", par);

    // start state machine for monitoring daytime
    t.ephemera(t.state_changer(name, state));
    t.trial_data(name, {comment: "starting",
        subject: par.subject,
        version: version,
        params: par});
    // hourly heartbeat messages for the activity monitor
    t.heartbeat(name, {subject: par.subject});

    // update feeder list
    t.get_feeders((err, feeders) => {
        if (!err) {
            logger.info("available feeders: ", feeders)
            par.feeders = feeders;
        }
    });

    start()
});

function shutdown() {
    t.trial_data(name, {comment: "stopping", subject: par.subject})
    t.disconnect(process.exit);
}

// disconnect will reset apparatus to base state
process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);

// state definitions

function intertrial(duration, next_state) {
    update_state({phase: "intertrial"});
    if (state.paused) {
        update_state({phase: "paused"})
        logger.debug("training is paused");
        _.delay(intertrial, 10000, duration, next_state);
    }
    else
        _.delay(next_state, duration);
}

function feed(feeder, duration, next_state) {
    update_state({phase: "feeding"})
    _.delay(t.change_state, par.feed_delay,
        feeder, { feeding: true, interval: duration})
    t.await(feeder, null, function(msg) { return msg.feeding == false }, next_state);
}

function block0_await() {
    const iti_var = 30000;
    const iti_min = 60*par.feed_duration;

    if (state.block < 0) {
        logger.info("entering block 0")
        state.trial = 0;
        t.trial_data(name, {comment: "new-block",
            subject: par.subject,
            experiment: "block-0"});
        update_state({block: 0, trial: state.trial, phase: "starting", paused: false})
    }
    update_state({block: 0, trial: state.trial + 1, phase: "awaiting-feeding"})
    const feeder = random_feeder();
    const iti = Math.random() * iti_var + iti_min;
    logger.debug("trial iti:", iti);
    const next = (state.trial < par.block_trials) ? block0_await : block1_await;
    const delay_next = _.partial(intertrial, iti, next)
    t.trial_data(name, {program: name,
        subject: par.subject,
        block: state.block,
        trial: state.trial,
        response: "NA",
        result: "feed"});
    feed(feeder, par.feed_duration, delay_next);
}

function block1_await() {

    // all units in ms
    const blink_duration = 5000;
    const iti_var = 30000;
    const iti_min = 60*par.feed_duration;
    let pecked = "timeout";
    const cue = "cue_" + par.cue_position + "_" + par.cue_color;
    const key = "peck_" + par.cue_position;

    // state setup
    if (state.block < 1) {
        logger.info("entering block 1");
        state.trial = 0;
        t.trial_data(name, {comment: "new-block",
            subject: par.subject,
            experiment: "block-1"});
    }
    update_state({block: 1, trial: state.trial + 1, phase: "awaiting-response"});

    t.change_state(cue, { trigger: null, brightness: 1});

    t.await("keys", blink_duration, _test, _exit);

    function _test(msg) {
        if (!msg) return true;
        else if (msg[key]) {
            pecked = key;
            return true;
        }
    }

    function _exit() {
        t.change_state(cue, { trigger: null, brightness: 0});
        const feeder = random_feeder();
        const iti = Math.random() * iti_var + iti_min;
        logger.debug("trial iti:", iti);
        const next = (state.trial < par.block_trials) ? block1_await : block2_await;
        const delay_next = _.partial(intertrial, iti, next);
        t.trial_data(name, {subject: par.subject,
            block: state.block,
            trial: state.trial,
            response: pecked,
            result: "feed"
        });
        feed(feeder, par.feed_duration, delay_next);
    }
}

function block2_await() {
    const iti_var = 10000;
    const iti_min = par.feed_duration;
    const cue = "cue_" + par.cue_position + "_" + par.cue_color;
    const key = "peck_" + par.cue_position;

    if (state.block < 2) {
        logger.info("entering block 2")
        state.trial = 0;
        t.trial_data(name, {comment: "new-block",
            subject: par.subject,
            experiment: "block-2"});
    }
    update_state({ block: 2, trial: state.trial + 1, phase: "awaiting-response"});
    t.change_state(cue, { trigger: null, brightness: 1});

    t.await("keys", null, function(msg) { return msg[key] }, _exit);

    function _exit() {
        t.change_state(cue, { trigger: null, brightness: 0});
        const feeder = random_feeder();
        const iti = Math.random() * iti_var + iti_min;
        logger.debug("trial iti:", iti);

        if (state.block == 2 && state.trial == par.block_trials && !argv.F) {
            logger.info("shape completed!")
            if (!argv["no-notify"])
                util.slack(format("shape completed for %s on %s. Trials will continue to run",
                        os.hostname(), par.subject),
                    par.user,
                    _.partial(logger.info, "sent message to", par.user))
        }

        const next = block2_await;
        const delay_next = _.partial(intertrial, iti, next);
        t.trial_data(name, {program: name,
            subject: par.subject,
            block: state.block,
            trial: state.trial,
            response: key,
            result: "feed"
        });
        feed(feeder, par.feed_duration, delay_next);
    }
}

/*function block3_peck1() {
    const cue = "cue_" + par.cue_position + "_" + par.cue_color;
    const key = "peck_" + par.cue_position;

    if (state.block < 3) {
        logger.info("entering block 3")
        state.trial = 0;
        t.trial_data(name, {comment: "new-block",
            subject: par.subject,
            experiment: "block-3"});
    }
    t.change_state(cue, { trigger: null, brightness: 1})
    update_state({ block: 3, trial: state.trial + 1, phase: "awaiting-response-1"});

    t.await("keys", null, function(msg) { return msg[key]}, function() {
        t.change_state(cue, { trigger: null, brightness: 0})
        block34_peck2(key);
    })
}

function block4_peck1() {
    const key = "peck_" + par.cue_position;

    if (state.block < 4) {
        logger.info("entering block 4")
        state.trial = 0;
        t.trial_data(name, {comment: "new-block",
            subject: par.subject,
            experiment: "block-4"});
    }
    update_state({ block: 4, trial: state.trial + 1, phase: "awaiting-response-1"});

    t.await("keys", null, function(msg) { return msg[key]}, _.partial(block34_peck2, key));
}

function block34_peck2(key) {
    const iti = par.feed_duration;
    const cue = "cue_" + par.cue_position + "_" + par.cue_color;

    t.change_state(cue, { trigger: null, brightness: 1})

    update_state({ phase: "awaiting-response-2"});
    t.await("keys", null, function(msg) { return msg[key]}, _exit);

    function _exit() {
        let next;
        t.change_state(cue, { trigger: null, brightness: 0});
        const feeder = pick_feeder("right");
        if (state.block == 3 && state.trial < par.block_trials)
            next = block3_peck1;
        else
            next = block4_peck1;

        if (state.block == 4 && state.trial == par.block_trials && !argv.F) {
            logger.info("shape completed!")
            if (!argv["no-notify"])
                util.slack(format("shape completed for %s on %s. Trials will continue to run",
                        os.hostname(), par.subject),
                    par.user,
                    _.partial(logger.info, "sent message to", par.user))
        }

        t.trial_data(name, {program: name,
            subject: par.subject,
            block: state.block,
            trial: state.trial,
            response: key,
            result: "feed"});
        feed(feeder, par.feed_duration, next);
    }
}*/

function random_feeder() {
    const r = Math.random();
    const i = Math.floor(r * par.feeders.length);
    logger.debug("random feeder:", r, par.feeders[i]);
    return par.feeders[i];
}


function pick_feeder(side) {
    const name = "feeder_" + side;
    if (_.has(par.feeders, name))
        return name;
    else
        return random_feeder();
}